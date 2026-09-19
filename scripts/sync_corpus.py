"""Upload corpus/*.md to the Knowledge Base docs bucket and run ingestion.

Each '## Section' becomes its own S3 object (the data source uses no extra
chunking), with a .metadata.json sidecar carrying title/heading/source so the
app can cite exactly where an answer came from.

Usage: python scripts/sync_corpus.py [--stack sahakar-saathi]
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import boto3

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"
PREFIX = "sections/"


def load_sections():
    """Each corpus file: '# Title', 'Source: ...', then '## Section' blocks."""
    sections = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        title, source, heading, lines = path.stem, "", None, []

        def flush():
            text = "\n".join(lines).strip()
            if heading and text:
                slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
                sections.append({
                    "key": f"{PREFIX}{path.stem}/{slug}.md",
                    "body": f"{title} — {heading}\n\n{text}\n",
                    "meta": {"title": title, "heading": heading, "source": source},
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
    return sections


def stack_outputs(stack):
    outputs = boto3.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", default="sahakar-saathi")
    args = parser.parse_args()

    out = stack_outputs(args.stack)
    bucket, kb_id, ds_id = out["DocsBucketName"], out["KnowledgeBaseId"], out["DataSourceId"]
    s3, agent = boto3.client("s3"), boto3.client("bedrock-agent")

    sections = load_sections()
    wanted = set()
    for s in sections:
        s3.put_object(Bucket=bucket, Key=s["key"], Body=s["body"].encode(), ContentType="text/markdown")
        s3.put_object(
            Bucket=bucket,
            Key=s["key"] + ".metadata.json",
            Body=json.dumps({"metadataAttributes": s["meta"]}, ensure_ascii=False).encode(),
            ContentType="application/json",
        )
        wanted |= {s["key"], s["key"] + ".metadata.json"}
    print(f"Uploaded {len(sections)} sections to s3://{bucket}/{PREFIX}")

    stale = [
        {"Key": o["Key"]}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX)
        for o in page.get("Contents", [])
        if o["Key"] not in wanted
    ]
    if stale:
        s3.delete_objects(Bucket=bucket, Delete={"Objects": stale})
        print(f"Removed {len(stale)} stale objects")

    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]
    print(f"Ingestion job {job['ingestionJobId']} started", end="", flush=True)
    while job["status"] in ("STARTING", "IN_PROGRESS"):
        time.sleep(5)
        print(".", end="", flush=True)
        job = agent.get_ingestion_job(
            knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job["ingestionJobId"]
        )["ingestionJob"]
    print(f"\nStatus: {job['status']}  stats: {json.dumps(job.get('statistics', {}))}")
    if job["status"] != "COMPLETE":
        print("Failure reasons:", job.get("failureReasons"))
        sys.exit(1)


if __name__ == "__main__":
    main()
