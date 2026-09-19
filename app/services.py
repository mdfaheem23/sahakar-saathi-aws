"""Thin wrappers around the AWS services the graph nodes use."""

import base64
import json
import os
import re
import time
import uuid

import boto3
from botocore.exceptions import ClientError

BUCKET = os.environ.get("AUDIO_BUCKET", "")
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-2-lite-v1:0")

s3 = boto3.client("s3")
transcribe = boto3.client("transcribe")
translate = boto3.client("translate")
polly = boto3.client("polly")
bedrock = boto3.client("bedrock-runtime")

LANGUAGES = {
    # code: (Transcribe/Polly language, Polly voice or None)
    "en": ("en-IN", "Kajal"),
    "hi": ("hi-IN", "Kajal"),
    "ta": ("ta-IN", None),  # Polly has no Tamil voice; answer is returned as text only
}
AUDIO_FORMATS = {"webm", "mp4", "ogg", "wav", "mp3", "m4a"}
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
NOT_FOUND = "I could not find this in the official documents I have. Please contact your PACS office or call the Kisan helpline."

SYSTEM_PROMPT = f"""You are Sahakar Saathi, a helpful assistant for Indian farmers and cooperative (PACS) members.
Answer the farmer's question using ONLY the numbered passages provided.
- Use simple words a farmer with little schooling would understand. 2 to 5 short sentences.
- Mention concrete numbers, deadlines, helpline numbers and documents when the passages contain them.
- Cite passages inline like [1] or [2].
- Plain text only: no markdown, no bold, no bullet symbols.
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Never invent rules, amounts, dates, phone numbers or examples that are not in the passages."""


class VoiceUnavailable(Exception):
    """Transcribe isn't usable on this account yet (e.g. a new account still activating)."""


def speech_to_text(audio_b64, fmt, lang):
    job = f"saathi-{uuid.uuid4().hex}"
    audio_key, transcript_key = f"audio/{job}.{fmt}", f"transcripts/{job}.json"
    s3.put_object(Bucket=BUCKET, Key=audio_key, Body=base64.b64decode(audio_b64))
    try:
        try:
            transcribe.start_transcription_job(
                TranscriptionJobName=job,
                LanguageCode=LANGUAGES[lang][0],
                MediaFormat="mp4" if fmt == "m4a" else fmt,
                Media={"MediaFileUri": f"s3://{BUCKET}/{audio_key}"},
                OutputBucketName=BUCKET,
                OutputKey=transcript_key,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "SubscriptionRequiredException":
                raise VoiceUnavailable() from exc
            raise
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
    try:
        return translate.translate_text(Text=text, SourceLanguageCode=source, TargetLanguageCode=target)["TranslatedText"]
    except ClientError as exc:
        # Amazon Translate can take a while to activate on new accounts; translate with Bedrock meanwhile
        print(f"Translate unavailable, using Bedrock: {exc.response['Error']['Code']}")
        return _bedrock_translate(text, source, target)


def _bedrock_translate(text, source, target):
    resp = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": (
            f"Translate the user's text from {LANGUAGE_NAMES[source]} to {LANGUAGE_NAMES[target]}. "
            "The text is about Indian farming, crop insurance (PMFBY) and government schemes, so use those meanings: "
            "காரீஃப் / खरीफ = Kharif (monsoon crop season), ராபி / रबी = Rabi (winter crop season), "
            "பயிர் காப்பீடு / फसल बीमा = crop insurance, பிரீமியம் / प्रीमियम = premium. "
            "Keep numbers, citations like [1], phone numbers and scheme names unchanged. "
            "Reply with the translation only."
        )}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 800, "temperature": 0},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


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
    spoken = re.sub(r"\[\d+\]|[*#_`]", "", text)  # don't read citation markers or stray markdown aloud
    audio = polly.synthesize_speech(
        Text=spoken[:2900], VoiceId=voice, Engine="neural", LanguageCode=LANGUAGES[lang][0], OutputFormat="mp3"
    )["AudioStream"].read()
    return base64.b64encode(audio).decode()
