# Sahakar Saathi (AWS)

**A voice-first, multilingual assistant for farmers and cooperative (PACS) members, built on AWS.**

Built for the WeMakeDevs × AWS **First Commit: Bharat Builds** hackathon (Sept 17–20, 2026) — *Ship It* track.

## The problem

Farmers and PACS members lose out on crop insurance (PMFBY) and government schemes they already qualify for.
The rules are written in English or Hindi, in legal language, and spread across many portals. Farmers who speak
Tamil or another regional language, or who can't read well, end up depending on middlemen or missing
claim deadlines.

See [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) for the full problem statement.

## What it does

1. The farmer **speaks or types** a question in Hindi, Tamil or English.
2. **Amazon Transcribe** converts speech to text.
3. **Amazon Translate** translates the question to English.
4. The app finds the relevant passages in official scheme documents (**Amazon Bedrock** Titan embeddings).
5. **Amazon Bedrock** (Claude) answers **only from those passages** and cites its sources. If the answer
   isn't in the documents, it says so instead of guessing.
6. **Amazon Translate** translates the answer back, and **Amazon Polly** reads it aloud.

```
Voice / text ──► Transcribe ──► Translate ──► Retrieve (Bedrock embeddings)
                                                   │
Voice reply ◄── Polly ◄── Translate ◄── Bedrock Claude (grounded answer + sources)
```

## AWS services used

| Service | Role |
|---|---|
| Amazon Transcribe | Speech → text (hi-IN, ta-IN, en-IN) |
| Amazon Translate | Question/answer translation |
| Amazon Bedrock – Titan Text Embeddings v2 | Semantic search over scheme documents |
| Amazon Bedrock – Claude | Grounded answer generation |
| Amazon Polly | Text → speech (Hindi, Indian English) |
| AWS Lambda + Function URL | Backend + serves the web app |
| Amazon S3 | Temporary audio storage (auto-deleted after 1 day) |
| AWS SAM / CloudFormation | Infrastructure as code |

## Project structure

```
app/            Lambda function (API + web UI)
  handler.py    Request routing and the voice → answer pipeline
  rag.py        Loads the corpus, embeds it, retrieves top passages
  static/       Frontend (single HTML page)
  corpus/       Source documents the assistant is allowed to answer from
template.yaml   AWS SAM template
```

## Deploy

Requires an AWS account with Bedrock model access enabled for Claude and Titan Text Embeddings v2.

```bash
brew install awscli aws-sam-cli
aws configure            # or: aws configure sso
sam build
sam deploy --guided      # first time; afterwards just `sam deploy`
```

The stack prints the live URL (`AppUrl`) when the deploy finishes.

## Limitations

- Amazon Polly has no Tamil voice, so Tamil answers come back as text only. Hindi and English answers are also read aloud.
- The corpus is a small starter set. The answers are only as good as the documents in `corpus/`.
- This is a hackathon prototype. It is not legal or financial advice.
