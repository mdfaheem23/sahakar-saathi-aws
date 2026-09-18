"""Lambda entry point (Function URL). Serves the web page and the /api/ask
pipeline: Transcribe -> Translate -> retrieve -> Bedrock -> Translate -> Polly."""

import base64
import json
import os
import time
import uuid
from pathlib import Path

import boto3

import rag

BUCKET = os.environ.get("AUDIO_BUCKET", "")
MODEL_ID = os.environ.get("MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
STATIC_DIR = Path(__file__).parent / "static"

s3 = boto3.client("s3")
transcribe = boto3.client("transcribe")
translate = boto3.client("translate")
polly = boto3.client("polly")
bedrock = boto3.client("bedrock-runtime")

LANGUAGES = {
    # code: (Transcribe language, Polly voice or None)
    "en": ("en-IN", "Kajal"),
    "hi": ("hi-IN", "Kajal"),
    "ta": ("ta-IN", None),  # Polly has no Tamil voice; answer is returned as text only
}
AUDIO_FORMATS = {"webm", "mp4", "ogg", "wav", "mp3", "m4a"}
NOT_FOUND = "I could not find this in the official documents I have. Please contact your PACS office or call the Kisan helpline."

SYSTEM_PROMPT = f"""You are Sahakar Saathi, a helpful assistant for Indian farmers and cooperative (PACS) members.
Answer the farmer's question using ONLY the numbered passages provided.
- Use simple words a farmer with little schooling would understand. 2 to 5 short sentences.
- Mention concrete numbers, deadlines, helpline numbers and documents when the passages contain them.
- Cite passages inline like [1] or [2].
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Never invent rules, amounts, dates or phone numbers."""


def respond(status, body, content_type="application/json"):
    if content_type == "application/json":
        body = json.dumps(body, ensure_ascii=False)
    return {"statusCode": status, "headers": {"Content-Type": content_type}, "body": body}


def speech_to_text(audio_b64, fmt, lang):
    job = f"saathi-{uuid.uuid4().hex}"
    audio_key, transcript_key = f"audio/{job}.{fmt}", f"transcripts/{job}.json"
    s3.put_object(Bucket=BUCKET, Key=audio_key, Body=base64.b64decode(audio_b64))
    try:
        transcribe.start_transcription_job(
            TranscriptionJobName=job,
            LanguageCode=LANGUAGES[lang][0],
            MediaFormat="mp4" if fmt == "m4a" else fmt,
            Media={"MediaFileUri": f"s3://{BUCKET}/{audio_key}"},
            OutputBucketName=BUCKET,
            OutputKey=transcript_key,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            status = transcribe.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
            state = status["TranscriptionJobStatus"]
            if state == "COMPLETED":
                data = json.loads(s3.get_object(Bucket=BUCKET, Key=transcript_key)["Body"].read())
                return data["results"]["transcripts"][0]["transcript"].strip()
            if state == "FAILED":
                raise RuntimeError(status.get("FailureReason", "Transcription failed"))
            time.sleep(1)
        raise TimeoutError("Transcription took too long")
    finally:
        s3.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": audio_key}, {"Key": transcript_key}]})


def translate_text(text, source, target):
    if source == target or not text:
        return text
    return translate.translate_text(Text=text, SourceLanguageCode=source, TargetLanguageCode=target)["TranslatedText"]


def generate_answer(question, passages):
    context = "\n\n".join(
        f"[{i}] {p['title']} — {p['heading']}\n{p['text']}" for i, p in enumerate(passages, 1)
    )
    resp = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": f"Passages:\n{context}\n\nQuestion: {question}"}]}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


def text_to_speech(text, lang):
    voice = LANGUAGES[lang][1]
    if not voice:
        return None
    audio = polly.synthesize_speech(
        Text=text[:2900], VoiceId=voice, Engine="neural", LanguageCode=LANGUAGES[lang][0], OutputFormat="mp3"
    )["AudioStream"].read()
    return base64.b64encode(audio).decode()


def ask(payload):
    lang = payload.get("lang", "en")
    if lang not in LANGUAGES:
        return respond(400, {"error": f"Unsupported language: {lang}"})

    question = (payload.get("text") or "").strip()
    if payload.get("audio"):
        fmt = payload.get("format", "webm")
        if fmt not in AUDIO_FORMATS:
            return respond(400, {"error": f"Unsupported audio format: {fmt}"})
        question = speech_to_text(payload["audio"], fmt, lang)
    if not question:
        return respond(400, {"error": "Please say or type a question."})
    question = question[:1000]

    question_en = translate_text(question, lang, "en")
    passages = rag.retrieve(question_en)
    answer_en = generate_answer(question_en, passages)
    answer = translate_text(answer_en, "en", lang)

    return respond(200, {
        "question": question,
        "question_en": question_en,
        "answer": answer,
        "answer_en": answer_en,
        "audio": text_to_speech(answer, lang),
        "sources": [
            {"n": i, "title": p["title"], "heading": p["heading"], "source": p["source"], "score": p["score"]}
            for i, p in enumerate(passages, 1)
        ],
    })


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")

    if method == "GET" and path in ("/", "/index.html"):
        return respond(200, (STATIC_DIR / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
    if method == "GET" and path == "/api/health":
        return respond(200, {"ok": True})
    if method == "POST" and path == "/api/ask":
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        try:
            return ask(json.loads(body))
        except Exception as exc:  # surface a readable error to the UI instead of a bare 502
            print(f"ask failed: {exc!r}")
            return respond(500, {"error": "Something went wrong. Please try again."})
    return respond(404, {"error": "Not found"})
