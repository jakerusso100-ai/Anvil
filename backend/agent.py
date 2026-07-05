"""Anvil agent loop — multi-step tool use for local (Ollama) and API (Anthropic) models.

Yields event dicts: stage / delta / tool_call / tool_result / approval_denied / final.
Approval: caller supplies `approve(name, args) -> bool` (UI blocks the worker thread
on a dialog; benchmarks pass lambda: True).

Checkpoints: before any write_file/edit_file, the original file is copied to
<workspace>/.anvil/checkpoints/<run_id>/ so the UI can offer one-click restore.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Callable, Iterator

import requests

import llm
import tools

MAX_STEPS = 40  # room for hard builds (3D games) to converge on a clean self-test

AGENT_SYSTEM = (
    "You are Anvil, an agentic coding assistant working in the user's workspace. "
    "Use the available tools to explore, read, write, edit files, run commands, and "
    "search the web as needed. Work step by step: inspect before you edit, verify "
    "after you change (run the code or tests with bash). Prefer small targeted edits. "
    "When you build a GUI program (a game or windowed app), do NOT run it directly to "
    "test — it would open a blocking window. Instead give it a headless self-test path "
    "(e.g. a --selftest or --frames N flag that runs a fixed number of frames and exits "
    "with code 0), and run THAT. Your shell already forces GUI toolkits headless. "
    "When the task is complete, give a brief summary of what you did."
)


def _vault_note() -> str:
    if tools.VAULT_PATH:
        return ("\n\nThe user's Obsidian notes vault is connected. Use vault_search / "
                "vault_read when their notes, projects, or past decisions are relevant; "
                "vault_write to save notes when asked.")
    return ""


def _project_instructions(workspace: str) -> str:
    out = ""
    for name in ("ANVIL.md", "CLAUDE.md", ".cursorrules"):
        p = Path(workspace) / name
        if p.exists():
            try:
                out += f"\n\nProject instructions ({name}):\n" + p.read_text(encoding="utf-8")[:8000]
                break
            except Exception:
                pass
    mem = Path(workspace) / ".anvil" / "memory.md"
    if mem.exists():
        try:
            body = mem.read_text(encoding="utf-8")[:6000]
            out += ("\n\nWhat you've learned about this project in past sessions "
                    "(use it; don't re-derive):\n" + body)
        except Exception:
            pass
    return out


def run_hooks(event: str, workspace: str, context: dict) -> str:
    """Run configured shell hooks (~/.anvil/hooks.json) for an event like
    'post_edit' or 'pre_bash'. {event: "cmd with {path} placeholders"}."""
    import json as _json
    import subprocess as _sp
    cfg = Path.home() / ".anvil" / "hooks.json"
    try:
        hooks = _json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return ""
    cmd = hooks.get(event)
    if not cmd:
        return ""
    try:
        for k, v in context.items():
            cmd = cmd.replace("{" + k + "}", str(v))
        r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=workspace)
        return f"[hook {event}] exit {r.returncode} {(r.stdout or r.stderr)[:200]}"
    except Exception as e:
        return f"[hook {event}] failed: {e}"


def _checkpoint(workspace: str, run_id: str, rel_path: str) -> None:
    src = Path(workspace) / rel_path
    if src.exists() and src.is_file():
        dst = Path(workspace) / ".anvil" / "checkpoints" / run_id / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():  # keep the FIRST pre-edit version
            shutil.copy2(src, dst)


def restore_checkpoint(workspace: str, run_id: str) -> list[str]:
    root = Path(workspace) / ".anvil" / "checkpoints" / run_id
    restored = []
    if root.exists():
        for f in root.rglob("*"):
            if f.is_file():
                rel = f.relative_to(root)
                shutil.copy2(f, Path(workspace) / rel)
                restored.append(str(rel))
    return restored


def restore_file(workspace: str, run_id: str, rel_path: str) -> bool:
    """Reject one edit: restore a single file from the run's checkpoint.
    If the file didn't exist before the run (no snapshot), delete it."""
    snap = Path(workspace) / ".anvil" / "checkpoints" / run_id / rel_path
    target = Path(workspace) / rel_path
    if snap.is_file():
        shutil.copy2(snap, target)
        return True
    if target.is_file():
        target.unlink()
        return True
    return False


def _read_or_empty(workspace: str, rel: str) -> str:
    p = Path(workspace) / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    except Exception:
        return ""


def _run_subagent(task: str, model: str, workspace: str, run_id: str,
                  approve: Callable, depth: int) -> str:
    """Nested agent loop for a delegated subtask. Returns a text summary only;
    the subagent's step-by-step chatter stays out of the parent's context."""
    if depth >= 2:
        return "ERROR: subagent depth limit reached (no further delegation)"
    answer, tool_calls = "", 0
    for ev in _dispatch_agent(model, [{"role": "user", "content": task}],
                              workspace, run_id + f"-sub{depth}", approve, depth + 1):
        if ev["type"] == "tool_call":
            tool_calls += 1
        elif ev["type"] == "final_text":
            answer = ev.get("answer") or ""
    return f"[subagent completed: {tool_calls} tool calls]\n{answer}"


# set by run_agent so subagents reuse the same model; overridable
_ACTIVE_MODEL = {"name": None, "approve": None}


def _exec_tool(name: str, args: dict, workspace: str, run_id: str,
               approve: Callable[[str, dict], bool], depth: int = 0) -> tuple[str, bool, dict | None]:
    """Returns (result_text, was_denied, diff_info)."""
    if tools.is_dangerous(name) and not approve(name, args):
        return ("User denied this action. Ask before retrying or choose another approach.",
                True, None)
    if name == "spawn_subagent":
        model = _ACTIVE_MODEL["name"] or "gpt-oss:20b"
        return _run_subagent(args.get("task", ""), model, workspace, run_id, approve, depth), False, None
    diff = None
    is_edit = name in ("write_file", "edit_file") and args.get("path")
    before = _read_or_empty(workspace, args["path"]) if is_edit else ""
    if is_edit:
        _checkpoint(workspace, run_id, args["path"])
    result = tools.run_tool(name, args, workspace)
    if is_edit and not result.startswith("ERROR"):
        diff = {"path": args["path"], "before": before,
                "after": _read_or_empty(workspace, args["path"])}
        hook = run_hooks("post_edit", workspace, {"path": args.get("path", "")})
        if hook:
            result += "\n" + hook
    elif name == "bash":
        hook = run_hooks("post_bash", workspace, {"command": args.get("command", "")})
        if hook:
            result += "\n" + hook
    return result, False, diff


# ---------------- Ollama agent loop (native tool calling) ----------------

def _ollama_step(model: str, messages: list[dict]) -> dict:
    r = requests.post(
        f"{llm.OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": False,
              "tools": tools.ollama_tools(), "options": {"num_predict": 8192}},
        timeout=1200,
    )
    r.raise_for_status()
    return r.json()["message"]


def run_agent_ollama(model: str, messages: list[dict], workspace: str, run_id: str,
                     approve: Callable, depth: int = 0) -> Iterator[dict]:
    system = AGENT_SYSTEM + _vault_note() + _project_instructions(workspace)
    msgs = [{"role": "system", "content": system}] + messages
    for step in range(MAX_STEPS):
        yield {"type": "stage", "stage": "thinking", "model": model, "step": step + 1}
        m = _ollama_step(model, msgs)
        msgs.append(m)
        calls = m.get("tool_calls") or []
        if m.get("content"):
            yield {"type": "delta", "channel": "agent", "round": 0, "text": m["content"]}
        if not calls:
            yield {"type": "final_text", "answer": m.get("content", "")}
            return
        for c in calls:
            fn = c.get("function", {})
            name, args = fn.get("name"), fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            yield {"type": "tool_call", "name": name, "args": args}
            result, denied, diff = _exec_tool(name, args, workspace, run_id, approve, depth)
            yield {"type": "tool_result", "name": name, "output": result, "denied": denied,
                   "diff": diff, "run_id": run_id}
            msgs.append({"role": "tool", "content": result, "tool_name": name})
    yield {"type": "final_text", "answer": "(agent hit the step limit)"}


# ---------------- Anthropic agent loop ----------------

def run_agent_anthropic(model: str, messages: list[dict], workspace: str, run_id: str,
                        approve: Callable, depth: int = 0) -> Iterator[dict]:
    import anthropic

    client = anthropic.Anthropic()
    system = AGENT_SYSTEM + _vault_note() + _project_instructions(workspace)
    msgs = [dict(m) for m in messages]
    total_cost = 0.0
    kwargs = {"model": model, "max_tokens": 8000, "system": system,
              "tools": tools.anthropic_tools()}
    if any(k in model for k in ("opus-4-6", "opus-4-7", "opus-4-8", "sonnet-4-6", "sonnet-5")):
        kwargs["thinking"] = {"type": "adaptive"}
    use_beta = model.startswith("claude-fable")
    if use_beta:
        kwargs["betas"] = ["server-side-fallback-2026-06-01"]
        kwargs["extra_body"] = {"fallbacks": [{"model": "claude-opus-4-8"}]}
    api = client.beta.messages if use_beta else client.messages

    for step in range(MAX_STEPS):
        yield {"type": "stage", "stage": "thinking", "model": model, "step": step + 1}
        resp = api.create(messages=msgs, **kwargs)
        pi, po = llm.ANTHROPIC_PRICES.get(model, (0, 0))
        total_cost += resp.usage.input_tokens / 1e6 * pi + resp.usage.output_tokens / 1e6 * po
        if resp.stop_reason == "refusal":
            yield {"type": "final_text", "answer": "(request declined by safety system)",
                   "cost": round(total_cost, 5)}
            return
        text = "".join(b.text for b in resp.content if b.type == "text")
        if text:
            yield {"type": "delta", "channel": "agent", "round": 0, "text": text}
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        msgs.append({"role": "assistant", "content": resp.content})
        if not tool_uses:
            yield {"type": "final_text", "answer": text, "cost": round(total_cost, 5)}
            return
        results = []
        for tu in tool_uses:
            yield {"type": "tool_call", "name": tu.name, "args": tu.input}
            result, denied, diff = _exec_tool(tu.name, dict(tu.input), workspace, run_id, approve, depth)
            yield {"type": "tool_result", "name": tu.name, "output": result, "denied": denied,
                   "diff": diff, "run_id": run_id}
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": result})
        msgs.append({"role": "user", "content": results})
    yield {"type": "final_text", "answer": "(agent hit the step limit)", "cost": round(total_cost, 5)}


# ---------------- OpenAI-compatible agent loop (LM Studio, OpenRouter, z.ai) ----------------

def _openai_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in tools._active_specs()]


def run_agent_openai(base_url: str, real_model: str, api_key: str | None,
                     prices: tuple, messages: list[dict], workspace: str, run_id: str,
                     approve: Callable, depth: int = 0) -> Iterator[dict]:
    system = AGENT_SYSTEM + _vault_note() + _project_instructions(workspace)
    msgs = [{"role": "system", "content": system}] + [dict(m) for m in messages]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    total_cost = 0.0
    for step in range(MAX_STEPS):
        yield {"type": "stage", "stage": "thinking", "model": real_model, "step": step + 1}
        try:
            r = requests.post(f"{base_url}/chat/completions", headers=headers,
                              json={"model": real_model, "messages": msgs,
                                    "tools": _openai_tools(), "tool_choice": "auto",
                                    "max_tokens": 8192}, timeout=1200)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            yield {"type": "final_text", "answer": f"(agent error: {type(e).__name__}: {e})"}
            return
        usage = data.get("usage") or {}
        total_cost += (usage.get("prompt_tokens", 0) / 1e6 * prices[0]
                       + usage.get("completion_tokens", 0) / 1e6 * prices[1])
        msg = data["choices"][0]["message"]
        msgs.append(msg)
        if msg.get("content"):
            yield {"type": "delta", "channel": "agent", "round": 0, "text": msg["content"]}
        calls = msg.get("tool_calls") or []
        if not calls:
            yield {"type": "final_text", "answer": msg.get("content", ""),
                   "cost": round(total_cost, 5)}
            return
        for c in calls:
            fn = c.get("function", {})
            name = fn.get("name")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "name": name, "args": args}
            result, denied, diff = _exec_tool(name, args, workspace, run_id, approve, depth)
            yield {"type": "tool_result", "name": name, "output": result, "denied": denied,
                   "diff": diff, "run_id": run_id}
            msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
    yield {"type": "final_text", "answer": "(agent hit the step limit)",
           "cost": round(total_cost, 5)}


def _dispatch_agent(model: str, messages: list[dict], workspace: str, run_id: str,
                    approve: Callable, depth: int = 0) -> Iterator[dict]:
    remote = llm.remote_provider_for(model)
    if llm.is_api_model(model):
        return run_agent_anthropic(model, messages, workspace, run_id, approve, depth)
    if remote:
        prov, real_id = remote
        key = __import__("os").environ.get(prov["api_key_env"])
        if not key:
            return iter([{"type": "final_text",
                          "answer": f"{prov['name']} needs {prov['api_key_env']} set to use agent mode."}])
        spec = next((m for m in prov["models"] if m["id"] == real_id), {})
        return run_agent_openai(prov["base_url"], real_id, key,
                                (spec.get("price_in", 0), spec.get("price_out", 0)),
                                messages, workspace, run_id, approve, depth)
    if model.startswith(llm.LMS_PREFIX):
        return run_agent_openai(llm.LMSTUDIO_URL, model[len(llm.LMS_PREFIX):], None, (0, 0),
                                messages, workspace, run_id, approve, depth)
    return run_agent_ollama(model, messages, workspace, run_id, approve, depth)


def run_agent(model: str, messages: list[dict], workspace: str,
              approve: Callable[[str, dict], bool] = lambda n, a: True) -> Iterator[dict]:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    yield {"type": "run_started", "run_id": run_id}
    _ACTIVE_MODEL["name"] = model
    gen = _dispatch_agent(model, messages, workspace, run_id, approve, depth=0)
    total_cost = 0.0
    try:
        for ev in gen:
            if ev.get("cost"):
                total_cost = ev["cost"]
            yield ev
    except Exception as e:
        # any unhandled model/tool failure surfaces as a clean message, never a crash
        yield {"type": "final_text", "answer": f"(agent stopped on error: {type(e).__name__}: {e})"}
    yield {"type": "final", "cost": total_cost, "reviewed": False, "revised": False,
           "passed": None, "answer": "", "run_id": run_id}
