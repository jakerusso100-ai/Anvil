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
import subprocess

import requests

import llm

# The roster is the output of the gauntlet stress campaign (2026-07-04).
ROSTER = {
    "fast":     "gpt-oss:20b",              # 0.88 hard @ 167 t/s
    "apps":     "qwen3-coder-next:latest",  # 1.00 app suite @ 28 t/s
    "balanced": "qwen3-coder:30b",          # 0.88/0.84
    "vision":   "qwen2.5vl:7b",             # coding-vision bake-off winner (2026-07-06):
                                            # aced UI->spec, code OCR+bug, error-screenshot
                                            # debug; 2-3x faster than qwen3-vl:8b (which
                                            # returned nothing on the error traceback)
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


# ---------------- VRAM-fit guardrail ----------------
# A model bigger than VRAM spills onto the CPU and crawls — on a 16GB card the 52GB
# apps model runs ~72% on CPU and a single big generation can blow past Ollama's read
# timeout. So after routing, if the picked local model won't fit, swap down to the
# best-quality installed roster model that does. The paid-review loop makes up the gap.

FIT_HEADROOM = 0.9   # leave VRAM for the KV cache / context window
_VRAM: dict[str, int | None] = {}


def _probe_vram() -> int | None:
    """Total NVIDIA VRAM in bytes (summed across GPUs), or None if unavailable."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return None
        mib = sum(int(x) for x in out.stdout.split() if x.strip().isdigit())
        return mib * 1024 * 1024 if mib else None
    except Exception:
        return None


def _vram_budget() -> int | None:
    if "b" not in _VRAM:
        _VRAM["b"] = _probe_vram()
    return _VRAM["b"]


def _local_model_sizes() -> dict[str, int]:
    """Installed Ollama model -> on-disk size in bytes (a good VRAM-footprint proxy)."""
    try:
        r = requests.get(f"{llm.OLLAMA_URL}/api/tags", timeout=3)
        return {m["name"]: m.get("size", 0) for m in r.json().get("models", [])}
    except Exception:
        return {}


def fit_to_vram(model: str) -> tuple[str, str | None]:
    """If `model` won't fit in VRAM, swap to the best local roster model that does.
    Returns (model, note) — note explains the swap, or is None when nothing changed."""
    if llm.is_api_model(model) or model.startswith(llm.LMS_PREFIX):
        return model, None
    vram = _vram_budget()
    if not vram:
        return model, None  # can't measure — leave the pick alone
    sizes = _local_model_sizes()
    budget = int(vram * FIT_HEADROOM)
    if sizes.get(model, 0) <= budget:
        return model, None  # fits (or size unknown -> assume ok)
    installed = set(sizes)
    for key in ("apps", "balanced", "fast"):   # best quality that still fits
        cand = ROSTER[key]
        if cand != model and cand in installed and 0 < sizes.get(cand, 1 << 62) <= budget:
            gb = lambda b: f"{b / 2 ** 30:.0f}GB"
            return cand, f"{model} ({gb(sizes[model])}) won't fit ~{gb(budget)} VRAM -> {cand} + review"
    return model, None  # nothing smaller fits either; keep the original


def route(request: str, router_model: str = DEFAULT_ROUTER,
          allow_api: bool = True) -> dict:
    """Returns {model, category, why, router_ok, fit_note}."""
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
    note = None
    if not key.startswith("api"):
        # verify the local pick is actually installed; degrade gracefully
        installed = set(llm.list_local_models())
        if model not in installed:
            model = ROSTER["fast"] if ROSTER["fast"] in installed else next(iter(installed), ROSTER["api_hard"])
        model, note = fit_to_vram(model)  # don't hand back a model that won't fit VRAM
    if note:
        why = (why + " · " + note) if why else note
    return {"model": model, "category": cat, "why": why, "router_ok": ok, "fit_note": note}


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
