"""Shared pipeline: coder -> gated frontier review -> auto-fix loop.

Pure generator of event dicts (same event shapes as the web backend's SSE),
so any frontend — Qt desktop, web, CLI — can drive it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
import llm  # noqa: E402

CODER_SYSTEM = (
    "You are an expert coding assistant. Write correct, complete, runnable code. "
    "When you write code, put it in fenced code blocks and briefly explain it."
)


def run_turn(model: str, messages: list[dict], *, review: bool = True,
             reviewer: str = "claude-haiku-4-5", auto_revise: bool = True,
             max_rounds: int = 2) -> Iterator[dict]:
    user_request = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    total_cost = 0.0

    yield {"type": "stage", "stage": "coding", "model": model}
    produced = ""
    try:
        for ev in llm.stream_chat(model, messages, system=CODER_SYSTEM):
            if ev["type"] == "delta":
                produced += ev["text"]
                yield {"type": "delta", "channel": "coder", "round": 0, "text": ev["text"]}
            elif ev["type"] == "done":
                total_cost += ev["usage"].cost_usd
    except Exception as e:
        # coder model failed (no key, network, bad model) — report cleanly, don't crash
        yield {"type": "review_error", "error": f"coder model failed: {type(e).__name__}: {e}"}
        yield {"type": "final", "cost": round(total_cost, 5), "reviewed": False,
               "revised": False, "passed": None, "answer": produced}
        return

    if not (review and llm.looks_like_code(produced)):
        yield {"type": "final", "cost": round(total_cost, 5), "reviewed": False,
               "revised": False, "passed": None, "answer": produced}
        return

    revised_any = False
    passed = False
    for round_i in range(1, max_rounds + 1):
        yield {"type": "stage", "stage": "reviewing", "model": reviewer, "round": round_i}
        try:
            rev, rusage = llm.review_code(reviewer, user_request, produced)
            total_cost += rusage.cost_usd
        except Exception as e:
            yield {"type": "review_error", "error": str(e)}
            break

        yield {"type": "review", "round": round_i, "verdict": rev["verdict"],
               "summary": rev["summary"], "issues": rev["issues"],
               "reviewer": reviewer, "cost": round(rusage.cost_usd, 5)}

        if rev["verdict"] == "pass":
            passed = True
            break
        if not auto_revise or not rev.get("revision_instruction") or round_i == max_rounds:
            break

        yield {"type": "stage", "stage": "revising", "model": model, "round": round_i}
        revise_msgs = messages + [
            {"role": "assistant", "content": produced},
            {"role": "user", "content":
                "A senior reviewer found issues with your code. Fix ALL of them and return "
                "the complete corrected solution as one code block.\n\nReviewer instruction:\n"
                + rev["revision_instruction"]},
        ]
        new_produced = ""
        try:
            for ev in llm.stream_chat(model, revise_msgs, system=CODER_SYSTEM):
                if ev["type"] == "delta":
                    new_produced += ev["text"]
                    yield {"type": "delta", "channel": "revision", "round": round_i, "text": ev["text"]}
                elif ev["type"] == "done":
                    total_cost += ev["usage"].cost_usd
        except Exception as e:
            yield {"type": "review_error", "error": f"revision failed: {type(e).__name__}: {e}"}
            break
        produced = new_produced
        revised_any = True

    yield {"type": "final", "cost": round(total_cost, 5), "reviewed": True,
           "revised": revised_any, "passed": passed, "answer": produced}
