"""Lambda entry point (Function URL). Serves the web page and runs the
LangGraph assistant for POST /api/ask."""

import base64
import json
from pathlib import Path

from graph import saathi
from services import AUDIO_FORMATS, LANGUAGES

STATIC_DIR = Path(__file__).parent / "static"


def respond(status, body, content_type="application/json"):
    if content_type == "application/json":
        body = json.dumps(body, ensure_ascii=False)
    return {"statusCode": status, "headers": {"Content-Type": content_type}, "body": body}


def ask(payload):
    lang = payload.get("lang", "en")
    if lang not in LANGUAGES:
        return respond(400, {"error": f"Unsupported language: {lang}"})

    state = {"lang": lang, "question": (payload.get("text") or "").strip()[:1000]}
    if payload.get("audio"):
        fmt = payload.get("format", "webm")
        if fmt not in AUDIO_FORMATS:
            return respond(400, {"error": f"Unsupported audio format: {fmt}"})
        state.update(audio=payload["audio"], format=fmt)
    elif not state["question"]:
        return respond(400, {"error": "Please say or type a question."})

    result = saathi.invoke(state)
    if not result.get("question"):
        return respond(400, {"error": "Sorry, I couldn't hear a question. Please try again."})

    return respond(200, {
        "question": result["question"],
        "question_en": result["question_en"],
        "answer": result["answer"],
        "answer_en": result["answer_en"],
        "audio": result.get("audio_out"),
        "sources": [
            {"n": i, "title": p["title"], "heading": p["heading"], "source": p["source"], "score": p["score"]}
            for i, p in enumerate(result["passages"], 1)
        ],
    })


def lambda_handler(event, _context):
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
