"""Retrieval from the Amazon Bedrock Knowledge Base (vectors stored in Amazon S3 Vectors)."""

import os

import boto3

KNOWLEDGE_BASE_ID = os.environ.get("KNOWLEDGE_BASE_ID", "")

_kb = boto3.client("bedrock-agent-runtime")


def retrieve(question, k=4):
    resp = _kb.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": question},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": k}},
    )
    passages = []
    for r in resp["retrievalResults"]:
        meta = r.get("metadata", {})
        passages.append({
            "title": meta.get("title", "Document"),
            "heading": meta.get("heading", ""),
            "source": meta.get("source", ""),
            "text": r["content"]["text"],
            "score": round(r.get("score", 0.0), 3),
        })
    passages.sort(key=lambda p: p["score"], reverse=True)
    return passages
