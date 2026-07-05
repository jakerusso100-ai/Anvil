"""Anvil backend — FastAPI server for the local AI coding studio.

Endpoints:
  GET  /api/models              -> available local + API models, reviewer options
  POST /api/chat  (SSE stream)  -> coder streams; optional gated frontier review;
                                   optional auto-revise loop
  GET  /                        -> serves the frontend

Run:  py -3.14 -m uvicorn app:app --port 8000  (from anvil/backend)
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import llm

app = FastAPI(title="Anvil")
FRONTEND = Path(__file__).parent.parent / "frontend"

CODER_SYSTEM = (
    "You are an expert coding assistant. Write correct, complete, runnable code. "
    "When you write code, put it in fenced code blocks and briefly explain it."
)


class ChatReq(BaseModel):
    model: str
    messages: list[dict]
    review: bool = True
    reviewer: str = "claude-haiku-4-5"
    auto_revise: bool = True
    max_rounds: int = 2  # review->revise cycles before giving up


@app.get("/api/models")
def models():
    local = llm.list_local_models()
    return {
        "local": local,
        "api": llm.API_MODELS,
        "reviewers": llm.API_MODELS,
        "default_coder": _pick_default_coder(local),
        "default_reviewer": "claude-haiku-4-5",
    }


def _pick_default_coder(local: list[str]) -> str:
    for pref in ("gpt-oss:20b", "qwen3-coder:30b", "gemma3:12b"):
        if pref in local:
            return pref
    return local[0] if local else "claude-haiku-4-5"


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/chat")
def chat(req: ChatReq):
    return StreamingResponse(stream_turn(req), media_type="text/event-stream")


def stream_turn(req: ChatReq):
    messages = list(req.messages)
    user_request = next((m["content"] for m in reversed(messages)
                         if m["role"] == "user"), "")
    total_cost = 0.0

    # ---- Pass 1: coder ----
    yield _sse({"type": "stage", "stage": "coding", "model": req.model})
    produced = ""
    for ev in llm.stream_chat(req.model, messages, system=CODER_SYSTEM):
        if ev["type"] == "delta":
            produced += ev["text"]
            yield _sse({"type": "delta", "channel": "coder", "text": ev["text"]})
        elif ev["type"] == "done":
            total_cost += ev["usage"].cost_usd
            yield _sse({"type": "usage", "channel": "coder",
                        "in": ev["usage"].input_tokens, "out": ev["usage"].output_tokens,
                        "cost": round(ev["usage"].cost_usd, 5)})

    # ---- Gate: only review if enabled AND the turn produced code ----
    if not (req.review and llm.looks_like_code(produced)):
        yield _sse({"type": "final", "cost": round(total_cost, 5), "reviewed": False})
        return

    # ---- Review <-> revise loop: re-review each revision until pass or cap ----
    revised_any = False
    passed = False
    for round_i in range(1, req.max_rounds + 1):
        yield _sse({"type": "stage", "stage": "reviewing", "model": req.reviewer, "round": round_i})
        try:
            review, rusage = llm.review_code(req.reviewer, user_request, produced)
            total_cost += rusage.cost_usd
        except Exception as e:
            yield _sse({"type": "review_error", "error": str(e)})
            break

        yield _sse({"type": "review", "round": round_i, "verdict": review["verdict"],
                    "summary": review["summary"], "issues": review["issues"],
                    "reviewer": req.reviewer, "cost": round(rusage.cost_usd, 5)})

        if review["verdict"] == "pass":
            passed = True
            break
        if not req.auto_revise or not review.get("revision_instruction"):
            break
        if round_i == req.max_rounds:
            # out of rounds; leave the last revision as the answer
            break

        # local model revises using the reviewer's instruction
        yield _sse({"type": "stage", "stage": "revising", "model": req.model, "round": round_i})
        revise_msgs = messages + [
            {"role": "assistant", "content": produced},
            {"role": "user", "content":
                "A senior reviewer found issues with your code. Fix ALL of them and return the "
                "complete corrected solution as one code block.\n\nReviewer instruction:\n"
                + review["revision_instruction"]},
        ]
        new_produced = ""
        for ev in llm.stream_chat(req.model, revise_msgs, system=CODER_SYSTEM):
            if ev["type"] == "delta":
                new_produced += ev["text"]
                yield _sse({"type": "delta", "channel": "revision", "round": round_i, "text": ev["text"]})
            elif ev["type"] == "done":
                total_cost += ev["usage"].cost_usd
        produced = new_produced
        revised_any = True

    yield _sse({"type": "final", "cost": round(total_cost, 5), "reviewed": True,
                "revised": revised_any, "passed": passed})


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
