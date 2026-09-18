"""Tiny retrieval layer: split the corpus into sections, embed them with
Bedrock Titan, and return the passages closest to a question."""

import json
import os
from pathlib import Path

import boto3

EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
CORPUS_DIR = Path(__file__).parent / "corpus"

_bedrock = boto3.client("bedrock-runtime")
_index = None  # list of {"title", "source", "heading", "text", "vector"}; built once per container


def _embed(text):
    resp = _bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=json.dumps({"inputText": text[:8000], "dimensions": 512, "normalize": True}),
    )
    return json.loads(resp["body"].read())["embedding"]


def load_chunks():
    """Each corpus file: '# Title', 'Source: ...', then '## Section' blocks."""
    chunks = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        title, source, heading, lines = path.stem, "", None, []

        def flush():
            if heading and lines:
                chunks.append({
                    "title": title,
                    "source": source,
                    "heading": heading,
                    "text": "\n".join(lines).strip(),
                })

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("Source:"):
                source = line[len("Source:"):].strip()
            elif line.startswith("## "):
                flush()
                heading, lines = line[3:].strip(), []
            elif heading:
                lines.append(line)
        flush()
    return chunks


def _get_index():
    global _index
    if _index is None:
        _index = []
        for chunk in load_chunks():
            vector = _embed(f"{chunk['title']} — {chunk['heading']}\n{chunk['text']}")
            _index.append({**chunk, "vector": vector})
    return _index


def retrieve(question, k=4):
    q = _embed(question)
    scored = [
        (sum(a * b for a, b in zip(q, c["vector"])), c)  # vectors are normalized: dot == cosine
        for c in _get_index()
    ]
    scored.sort(key=lambda s: s[0], reverse=True)
    return [{**c, "score": round(s, 3)} for s, c in scored[:k]]
