# Sahakar Saathi — Multilingual Voice Assistant for Farmers & Cooperative Members

> Adapted from our SIH 2026 proposal (PS 26088, Ministry of Cooperation / NCCT) and scoped down for the
> WeMakeDevs × AWS "First Commit: Bharat Builds" hackathon (Sept 17–20, 2026). All code is written fresh during the event.

## Problem

Farmers and rural members of Primary Agricultural Credit Societies (PACS) regularly deal with crop insurance
(PMFBY), cooperative laws, and Ministry of Cooperation schemes — but most of them don't know their rights,
entitlements, or how to file a grievance. Three things cause this:

1. **Language barrier** — the official documents are almost entirely in English or Hindi, while rural users
   speak regional languages and dialects.
2. **Low digital and legal literacy** — even when the information exists, it is hard to read and act on.
3. **No single, trustworthy, always-available channel** — people rely on middlemen or word of mouth.

**Result:** eligible farmers miss PMFBY claim deadlines, PACS members don't know the by-laws that protect them,
and grievances go unfiled because the process is opaque.

## Solution (hackathon scope)

A voice-first, multilingual web assistant. A farmer asks a question by speaking in their own language (for example
Tamil) and gets a spoken answer in the same language. The answer is based only on official government documents
and names the source it came from.

**Example:** a farmer asks in Tamil, *"My crop was damaged by rain, can I claim PMFBY insurance?"* → the assistant
answers in Tamil voice with the eligibility window, required documents and deadline, and cites the PMFBY guideline.

### Core features (must ship)
- Voice or text question in a regional language (Tamil, Hindi, English)
- Answers grounded in a small verified corpus (PMFBY guidelines + 2–3 key schemes) with source citations
- Spoken reply in the user's language
- Refuses to guess when the answer isn't in the documents

### Stretch (only if time allows)
- Simple grievance form → ticket ID → check status

### Out of scope for this hackathon (from the original SIH plan)
- Hardware kiosk / IVR line, native mobile app, admin analytics dashboard, multi-agent router

## AWS architecture

| Need | AWS service |
|---|---|
| Speech → text | Amazon Transcribe |
| Translate question / answer | Amazon Translate |
| Grounded answers (RAG) over govt PDFs | Amazon Bedrock Knowledge Bases + S3 |
| LLM for answering | Amazon Bedrock (Claude) |
| Text → speech | Amazon Polly |
| API | AWS Lambda + API Gateway |
| Grievance tickets (stretch) | Amazon DynamoDB |
| Hosting (Ship It track) | AWS Amplify |

```
Voice (Tamil) → Transcribe → Translate → Bedrock KB (RAG over PMFBY/scheme PDFs in S3)
             → Answer + source → Translate → Polly → Voice reply (Tamil)
```

## Impact
- More farmers claim PMFBY and scheme benefits they already qualify for
- Less reliance on middlemen for legal or scheme information
- Language and literacy stop being barriers, because the assistant works entirely by voice in the user's language
