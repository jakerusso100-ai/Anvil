"""Anvil Copilot — the router/supervisor (Cursor's "Auto" mode, local-first).

Three jobs:
  1. route(request)   — classify the user's request with a small fast local model
                        and pick the right specialist from the roster.
  2. health()         — check Ollama, API key, roster models, LM Studio.
  3. fallback_for(m)  — pick the next model when one fails mid-run.
"""
from __future__ import annotations

import json
import os
import re

import requests

import llm

# The roster is the output of the gauntlet stress campaign (2026-07-04).
ROSTER = {
    "fast":     "gpt-oss:20b",              # 0.88 hard @ 167 t/s
    "apps":     "qwen3-coder-next:latest",  # 1.00 app suite @ 28 t/s
    "balanced": "qwen3-coder:30b",          # 0.88/0.84
    "vision":   "qwen3-vl:8b",              # 1.00 vision
    "api_hard": "claude-sonnet-5",          # 1.00 everywhere, cheap-ish
    "api_max":  "claude-opus-4-8",          # the big gun
}

ROUTE_TO_ROSTER = {
    "quick_question": "fast",
    "small_code": "fast",
    "build_app": "apps",
    "refactor_multi_file": "balanced",
    "hard_reasoning": "api_hard",
    "image_task": "vision",
}

DEFAULT_ROUTER = "granite4:latest"  # router_bench winner 2026-07-04: 100% acc, 2.6s

ROUTER_PROMPT = """Classify this coding-assistant request into exactly one category:
- quick_question: chat, explanations, simple questions
- small_code: single function, small edit, snippet, quick fix
- build_app: create a whole program/game/app/server from scratch
- refactor_multi_file: changes across several existing files
- hard_reasoning: tricky algorithms, math proofs, debugging subtle logic
- image_task: involves an image, screenshot, or visual content

Request: {request}

Reply with ONLY a JSON object: {{"category": "...", "why": "<8 words max>"}}"""


def route(request: str, router_model: str = DEFAULT_ROUTER,
          allow_api: bool = True) -> dict:
    """Returns {model, category, why, router_ok}."""
    try:
        r = requests.post(
            f"{llm.OLLAMA_URL}/api/chat",
            json={"model": router_model,
                  "messages": [{"role": "user", "content": ROUTER_PROMPT.format(request=request[:2000])}],
                  "stream": False, "format": "json",
                  "options": {"num_predict": 120, "temperature": 0}},
            timeout=60,
        )
        r.raise_for_status()
        data = json.loads(r.json()["message"]["content"])
        cat = data.get("category", "small_code")
        why = data.get("why", "")
        ok = True
    except Exception as e:
        cat, why, ok = "small_code", f"router unavailable ({type(e).__name__})", False
    key = ROUTE_TO_ROSTER.get(cat, "fast")
    if key.startswith("api") and not allow_api:
        key = "balanced"
    model = ROSTER[key]
    if key.startswith("api") is False:
        # verify the local pick is actually installed; degrade gracefully
        installed = set(llm.list_local_models())
        if model not in installed:
            model = ROSTER["fast"] if ROSTER["fast"] in installed else next(iter(installed), ROSTER["api_hard"])
    return {"model": model, "category": cat, "why": why, "router_ok": ok}


FALLBACK_CHAIN = [ROSTER["fast"], ROSTER["balanced"], ROSTER["api_hard"], ROSTER["api_max"]]


def fallback_for(failed_model: str, allow_api: bool = True) -> str | None:
    chain = [m for m in FALLBACK_CHAIN if m != failed_model]
    if not allow_api:
        chain = [m for m in chain if not llm.is_api_model(m)]
    installed = set(llm.list_local_models())
    for m in chain:
        if llm.is_api_model(m) or m in installed:
            return m
    return None


def health() -> list[dict]:
    """Component checks for the status bar."""
    out = []
    installed: set[str] = set()
    try:
        r = requests.get(f"{llm.OLLAMA_URL}/api/version", timeout=3)
        installed = set(llm.list_local_models())
        out.append({"name": "Ollama", "ok": True, "detail": f"v{r.json().get('version')} · {len(installed)} models"})
    except Exception as e:
        out.append({"name": "Ollama", "ok": False, "detail": f"unreachable: {type(e).__name__}"})
    missing = [m for k, m in ROSTER.items() if not k.startswith("api") and m not in installed]
    out.append({"name": "Roster", "ok": not missing,
                "detail": "all local roster models installed" if not missing else f"missing: {', '.join(missing)}"})
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    out.append({"name": "API", "ok": key,
                "detail": "Anthropic key present" if key else "no ANTHROPIC_API_KEY — reviews/escalation offline"})
    try:
        requests.get(f"{llm.LMSTUDIO_URL}/models", timeout=2)
        out.append({"name": "LM Studio", "ok": True, "detail": "server up (optional)"})
    except Exception:
        out.append({"name": "LM Studio", "ok": True, "detail": "off (optional)"})
    for p in llm.REMOTE_PROVIDERS:
        has = bool(os.environ.get(p["api_key_env"]))
        out.append({"name": p["name"], "ok": True,
                    "detail": (f"key present · {len(p['models'])} models" if has
                               else f"no {p['api_key_env']} — models hidden (optional)")})
    try:
        import mcp_client
        mcp_client.start()
        st = mcp_client.status()
        if st["servers"] or st["errors"]:
            ok = not st["errors"]
            detail = f"{len(st['servers'])} server(s), {st['tools']} tools"
            if st["errors"]:
                detail += " · errors: " + "; ".join(f"{k}: {v[:60]}" for k, v in st["errors"].items())
            out.append({"name": "MCP", "ok": ok, "detail": detail})
        else:
            out.append({"name": "MCP", "ok": True, "detail": "no servers configured (~/.anvil/mcp.json)"})
    except Exception as e:
        out.append({"name": "MCP", "ok": False, "detail": f"{type(e).__name__}: {e}"})
    return out
