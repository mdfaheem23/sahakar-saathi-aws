"""The assistant as a LangGraph state machine.

    START ─┬─(audio)─► transcribe ─┐
           └─(text)────────────────┴─► translate_in ─► retrieve ─┬─(relevant)──► generate ─┐
                                                                  └─(no match)──► not_found ┴─► translate_out ─► speak ─► END
"""

import os
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

import rag
import services

# Below this cosine similarity the best passage is treated as unrelated, so we
# answer "not found" without calling the LLM at all.
MIN_SCORE = float(os.environ.get("MIN_SCORE", "0.2"))


class SaathiState(TypedDict, total=False):
    lang: str
    audio: Optional[str]      # base64 audio from the browser
    format: Optional[str]     # audio container, e.g. "webm"
    question: str             # in the user's language
    question_en: str
    passages: list
    grounded: bool            # False when nothing relevant was retrieved
    answer_en: str
    answer: str               # in the user's language
    audio_out: Optional[str]  # base64 mp3 from Polly


def transcribe(state):
    return {"question": services.speech_to_text(state["audio"], state["format"], state["lang"])[:1000]}


def translate_in(state):
    return {"question_en": services.translate_text(state["question"], state["lang"], "en")}


def retrieve(state):
    passages = rag.retrieve(state["question_en"])
    return {"passages": passages, "grounded": bool(passages) and passages[0]["score"] >= MIN_SCORE}


def generate(state):
    return {"answer_en": services.generate_answer(state["question_en"], state["passages"])}


def not_found(state):
    return {"answer_en": services.NOT_FOUND, "passages": []}


def translate_out(state):
    return {"answer": services.translate_text(state["answer_en"], "en", state["lang"])}


def speak(state):
    return {"audio_out": services.text_to_speech(state["answer"], state["lang"])}


def build_graph():
    g = StateGraph(SaathiState)
    for name, fn in [
        ("transcribe", transcribe),
        ("translate_in", translate_in),
        ("retrieve", retrieve),
        ("generate", generate),
        ("not_found", not_found),
        ("translate_out", translate_out),
        ("speak", speak),
    ]:
        g.add_node(name, fn)

    g.add_conditional_edges(
        START, lambda s: "transcribe" if s.get("audio") else "translate_in", ["transcribe", "translate_in"]
    )
    g.add_edge("transcribe", "translate_in")
    g.add_edge("translate_in", "retrieve")
    g.add_conditional_edges("retrieve", lambda s: "generate" if s["grounded"] else "not_found", ["generate", "not_found"])
    g.add_edge("generate", "translate_out")
    g.add_edge("not_found", "translate_out")
    g.add_edge("translate_out", "speak")
    g.add_edge("speak", END)
    return g.compile()


saathi = build_graph()
