"""LLM adapters with streaming — Ollama (local) and Anthropic (API).

Distinct from gauntlet/providers.py (which is non-streaming, for benchmarking).
This module streams token-by-token for the chat UI and exposes a structured
`review()` call used by the quality-checker pipeline.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterator

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# $/1M tokens (input, output)
ANTHROPIC_PRICES = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
API_MODELS = list(ANTHROPIC_PRICES)

# Models that support adaptive thinking (Fable omits the param — always on).
_ADAPTIVE = ("opus-4-6", "opus-4-7", "opus-4-8", "sonnet-4-6", "sonnet-5")


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def is_api_model(model: str) -> bool:
    return model.startswith("claude-")


# ---------------- streaming chat ----------------

def stream_ollama(model: str, messages: list[dict]) -> Iterator[dict]:
    """Yield {'type':'delta','text':...} then {'type':'done','usage':Usage}."""
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True,
              "options": {"num_predict": 8192}},
        stream=True, timeout=1200,
    )
    r.raise_for_status()
    in_tok = out_tok = 0
    for line in r.iter_lines():
        if not line:
            continue
        d = json.loads(line)
        chunk = (d.get("message") or {}).get("content", "")
        if chunk:
            yield {"type": "delta", "text": chunk}
        if d.get("done"):
            in_tok = d.get("prompt_eval_count") or 0
            out_tok = d.get("eval_count") or 0
    yield {"type": "done", "usage": Usage(in_tok, out_tok, 0.0)}


def stream_anthropic(model: str, messages: list[dict], system: str | None = None) -> Iterator[dict]:
    import anthropic

    client = anthropic.Anthropic()
    kwargs = {"model": model, "max_tokens": 8000, "messages": messages}
    if system:
        kwargs["system"] = system
    if any(k in model for k in _ADAPTIVE):
        kwargs["thinking"] = {"type": "adaptive"}
    use_beta = model.startswith("claude-fable")
    if use_beta:
        kwargs["betas"] = ["server-side-fallback-2026-06-01"]
        kwargs["extra_body"] = {"fallbacks": [{"model": "claude-opus-4-8"}]}

    api = client.beta.messages if use_beta else client.messages
    in_tok = out_tok = 0
    with api.stream(**kwargs) as stream:
        for text in stream.text_stream:
            yield {"type": "delta", "text": text}
        final = stream.get_final_message()
        in_tok = final.usage.input_tokens
        out_tok = final.usage.output_tokens
    pi, po = ANTHROPIC_PRICES.get(model, (0, 0))
    cost = in_tok / 1e6 * pi + out_tok / 1e6 * po
    yield {"type": "done", "usage": Usage(in_tok, out_tok, cost)}


LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
LMS_PREFIX = "lms/"  # model ids namespaced to route to LM Studio


def _load_remote_providers() -> list[dict]:
    """Remote OpenAI-compatible providers (OpenRouter, z.ai, MiniMax...) from providers.json."""
    import pathlib
    import sys
    candidates = [
        pathlib.Path(getattr(sys, "_MEIPASS", "")) / "providers.json",   # frozen exe
        pathlib.Path(__file__).parent.parent / "providers.json",          # source tree
        pathlib.Path(sys.executable).parent / "providers.json",           # next to Anvil.exe
    ]
    for cfg in candidates:
        try:
            if cfg.is_file():
                return json.loads(cfg.read_text(encoding="utf-8")).get("remote_providers", [])
        except Exception:
            continue
    return []


REMOTE_PROVIDERS = _load_remote_providers()


def remote_provider_for(model: str) -> tuple[dict, str] | None:
    """If model is 'prefix/real-id' for a configured remote provider, return (provider, real_id)."""
    for p in REMOTE_PROVIDERS:
        pre = p["prefix"] + "/"
        if model.startswith(pre):
            return p, model[len(pre):]
    return None


def stream_openai_compat(base_url: str, model: str, messages: list[dict],
                         api_key: str | None = None,
                         prices: tuple[float, float] = (0.0, 0.0)) -> Iterator[dict]:
    """OpenAI-compatible streaming (LM Studio, OpenRouter, z.ai, llama.cpp, vLLM...)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages, "stream": True,
              "stream_options": {"include_usage": True}, "max_tokens": 8192},
        stream=True, timeout=1200,
    )
    r.raise_for_status()
    in_tok = out_tok = 0
    for line in r.iter_lines():
        if not line or not line.startswith(b"data: "):
            continue
        payload = line[6:]
        if payload.strip() == b"[DONE]":
            break
        d = json.loads(payload)
        if d.get("usage"):
            in_tok = d["usage"].get("prompt_tokens") or in_tok
            out_tok = d["usage"].get("completion_tokens") or out_tok
        for ch in d.get("choices", []):
            delta = (ch.get("delta") or {}).get("content")
            if delta:
                yield {"type": "delta", "text": delta}
    cost = in_tok / 1e6 * prices[0] + out_tok / 1e6 * prices[1]
    yield {"type": "done", "usage": Usage(in_tok, out_tok, cost)}


def stream_chat(model: str, messages: list[dict], system: str | None = None) -> Iterator[dict]:
    if is_api_model(model):
        yield from stream_anthropic(model, messages, system)
        return
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    remote = remote_provider_for(model)
    if remote:
        prov, real_id = remote
        key = os.environ.get(prov["api_key_env"])
        if not key:
            raise RuntimeError(f"{prov['name']} needs {prov['api_key_env']} set — "
                               f"get a key and set it, then restart Anvil")
        spec = next((m for m in prov["models"] if m["id"] == real_id), {})
        yield from stream_openai_compat(prov["base_url"], real_id, msgs, api_key=key,
                                        prices=(spec.get("price_in", 0), spec.get("price_out", 0)))
    elif model.startswith(LMS_PREFIX):
        yield from stream_openai_compat(LMSTUDIO_URL, model[len(LMS_PREFIX):], msgs)
    else:
        yield from stream_ollama(model, msgs)


# ---------------- structured review (the quality checker) ----------------

REVIEW_SYSTEM = (
    "You are a senior code reviewer verifying another model's work. Be precise and "
    "practical. Judge only real defects: bugs, missing requirements, crashes, wrong "
    "output, security issues. Ignore style unless it breaks correctness. If the code "
    "is correct and complete, pass it."
)

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["severity", "problem", "fix"],
                "additionalProperties": False,
            },
        },
        "revision_instruction": {"type": "string"},
    },
    "required": ["verdict", "summary", "issues", "revision_instruction"],
    "additionalProperties": False,
}


def review_code(reviewer_model: str, user_request: str, produced: str) -> tuple[dict, Usage]:
    """Have a frontier model check produced code against the request.

    Returns (structured_review, usage). Only meaningful for API reviewer models.
    """
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        f"The user asked a local model:\n<request>\n{user_request}\n</request>\n\n"
        f"The local model produced:\n<answer>\n{produced}\n</answer>\n\n"
        "Review it. If it fully satisfies the request and is correct, verdict 'pass'. "
        "Otherwise verdict 'revise', list concrete issues, and write a single clear "
        "'revision_instruction' the local model can act on to fix everything."
    )
    kwargs = {
        "model": reviewer_model,
        "max_tokens": 4000,
        "system": REVIEW_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
    }
    if any(k in reviewer_model for k in _ADAPTIVE):
        kwargs["thinking"] = {"type": "adaptive"}
    use_beta = reviewer_model.startswith("claude-fable")
    if use_beta:
        kwargs["betas"] = ["server-side-fallback-2026-06-01"]
        kwargs["extra_body"] = {"fallbacks": [{"model": "claude-opus-4-8"}]}

    api = client.beta.messages if use_beta else client.messages
    resp = api.create(**kwargs)
    if resp.stop_reason == "refusal":
        return ({"verdict": "pass", "summary": "Reviewer declined; skipping review.",
                 "issues": [], "revision_instruction": ""}, Usage())
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        review = json.loads(text)
    except json.JSONDecodeError:
        review = {"verdict": "pass", "summary": "Review unparseable; skipping.",
                  "issues": [], "revision_instruction": ""}
    pi, po = ANTHROPIC_PRICES.get(reviewer_model, (0, 0))
    usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens,
                  resp.usage.input_tokens / 1e6 * pi + resp.usage.output_tokens / 1e6 * po)
    return review, usage


CODE_FENCE = "```"


def looks_like_code(text: str) -> bool:
    """Cheap gate: only spend review budget when the turn actually produced code."""
    return text.count(CODE_FENCE) >= 2 or "def " in text or "class " in text or "function " in text


def fim_complete(prefix: str, suffix: str, model: str = "qwen2.5-coder:latest",
                 max_tokens: int = 64) -> str:
    """Fill-in-middle code completion (Cursor Tab). Uses Qwen FIM tokens.
    Returns the suggested continuation between prefix and suffix (may be '')."""
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "raw": True,
                  "options": {"num_predict": max_tokens, "temperature": 0.1,
                              "stop": ["<|fim_pad|>", "<|endoftext|>", "<|fim_prefix|>"]}},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("response", "")
    except Exception:
        return ""


def unload_ollama(model: str) -> None:
    """Free VRAM held by a model. Call when switching coders — a resident model
    starves the next one into a bad GPU split (measured: 30 t/s -> 3 t/s)."""
    try:
        requests.post(f"{OLLAMA_URL}/api/chat",
                      json={"model": model, "messages": [], "keep_alive": 0}, timeout=30)
    except Exception:
        pass


def list_remote_models() -> list[dict]:
    """Configured remote OpenAI-compat models: [{spec, label, has_key, provider}]."""
    out = []
    for p in REMOTE_PROVIDERS:
        has_key = bool(os.environ.get(p["api_key_env"]))
        for m in p["models"]:
            out.append({"spec": f"{p['prefix']}/{m['id']}", "label": m.get("label", m["id"]),
                        "has_key": has_key, "provider": p["name"]})
    return out


def list_local_models() -> list[str]:
    """Ollama models plus (if its server is up) LM Studio models as 'lms/<id>'."""
    models: list[str] = []
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models += sorted(m["name"] for m in r.json().get("models", []))
    except Exception:
        pass
    try:
        r = requests.get(f"{LMSTUDIO_URL}/models", timeout=3)
        models += sorted(f"{LMS_PREFIX}{m['id']}" for m in r.json().get("data", []))
    except Exception:
        pass
    return models
