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
    "Do the work yourself, writing files step by step — do NOT hand the entire task to "
    "a single subagent; reserve subagents for narrow, well-scoped sub-parts. "
    "To run Python use `python`; only fall back to `python3` if `python` is missing "
    "(on Windows `python3` is often a non-functional Store stub). Install deps with "
    "`python -m pip` so they land in the same interpreter you run. "
    "When the task is complete, give a brief summary of what you did."
)


PROMPT_MAKER_SYSTEM = (
    "You are Anvil's Prompt Builder. You do NOT write code or build anything — your only "
    "job is to interview the user and turn their rough idea into ONE precise, complete "
    "build prompt that a separate coding model can execute in a single shot.\n\n"
    "How to work:\n"
    "- Ask focused clarifying questions, a few at a time — never a wall of twenty. Ask a "
    "short round, then STOP and wait for the user's answer before asking more.\n"
    "- Cover the dimensions that actually matter for THIS kind of project. For a game: "
    "2D or 3D, genre, single- or multiplayer, controls, core mechanics, win/lose "
    "conditions, art/visual style, target language and library, and scope. For an app: "
    "platform, the core features, data and whether it must persist between runs, the UI, "
    "and the look and feel. Adapt the questions to what they actually asked for.\n"
    "- You MAY use web_search / web_fetch to check common conventions or libraries, "
    "vault_search / vault_read to pull the user's own notes or design docs, and "
    "read_file / list_dir / codebase_search to understand an existing project. Keep it "
    "light — the user is your main source, not the web.\n"
    "- Don't over-interview. After two to four short rounds, or as soon as you have "
    "enough, propose the finished prompt.\n\n"
    "When you are ready, output the final prompt EXACTLY in this form:\n"
    "===BUILD PROMPT===\n"
    "<the complete, self-contained prompt in plain language — specific and detailed, "
    "capturing everything the user asked for, and ending with an instruction to build it "
    "fully and self-test it headless before saying it's done>\n"
    "===END BUILD PROMPT===\n"
    "Then tell the user in one line that they can send it to the builder or ask you to "
    "tweak it."
)

_PROMPT_START = "===BUILD PROMPT==="
_PROMPT_END = "===END BUILD PROMPT==="


def extract_build_prompt(text: str) -> str | None:
    """Pull the finished build prompt out of a Prompt Maker message, if present."""
    if not text or _PROMPT_START not in text:
        return None
    body = text.split(_PROMPT_START, 1)[1]
    if _PROMPT_END in body:
        body = body.split(_PROMPT_END, 1)[0]
    return body.strip() or None


def _vault_query(messages: list[dict]) -> str:
    """The text to search the vault with — the user's request(s) in this turn."""
    return " ".join(m.get("content", "") for m in messages
                    if m.get("role") == "user" and isinstance(m.get("content"), str))[:2000]


def _vault_note() -> str:
    if tools.VAULT_PATH:
        return ("\n\nAn Obsidian knowledge vault is connected. BEFORE you web_search or "
                "trial-and-error your way through an unfamiliar library, framework, API, or "
                "error, vault_search it FIRST — the vault may hold a correct, ready-to-adapt "
                "pattern (a working skeleton, a self-test recipe, a known gotcha). Prefer "
                "vault_search over web_search for how-to-code questions; vault_read opens a "
                "note in full. Also use it for the user's own notes/decisions, and "
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

OLLAMA_STEP_TIMEOUT = 420  # one agent step; 8192 tokens fit this even for a slow model
# Explicit context window so we don't inherit a model's tiny 4K default (which silently
# drops early history on long builds). 16K is the sweet spot for a 16GB card.
OLLAMA_NUM_CTX = 16384
_CTX_BUDGET_CHARS = 44000   # ~ within 16K tokens; trim old tool output past this


def _manage_context(msgs: list[dict], keep_recent: int = 6) -> None:
    """Keep long agent runs inside the context window: when the conversation grows past
    the budget, truncate the CONTENT of OLD tool results (the bulkiest, least-needed-
    verbatim part) in place — so the system prompt, the task, and what files were written
    survive instead of Ollama silently dropping them. Recent steps are kept full."""
    total = sum(len(str(m.get("content", ""))) for m in msgs)
    if total <= _CTX_BUDGET_CHARS or len(msgs) <= keep_recent + 2:
        return
    for m in msgs[:-keep_recent]:
        c = m.get("content")
        if m.get("role") == "tool" and isinstance(c, str) and len(c) > 400:
            m["content"] = c[:300] + "\n[… older tool output trimmed to save context …]"


def _ollama_step(model: str, messages: list[dict]) -> dict:
    """One tool-calling turn against Ollama, hardened against transient instability:
    a bounded per-step timeout (so a hung server can't wedge the agent for 20 minutes)
    and a single retry on a transient failure (5xx / timeout / dropped connection)."""
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            r = requests.post(
                f"{llm.OLLAMA_URL}/api/chat",
                json={"model": model, "messages": messages, "stream": False,
                      "tools": tools.ollama_tools(),
                      "options": {"num_predict": 8192, "num_ctx": OLLAMA_NUM_CTX}},
                timeout=OLLAMA_STEP_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()["message"]
        except requests.HTTPError as e:
            last_err = e
            if e.response is None or e.response.status_code < 500:
                raise  # a 4xx is a real request problem; retrying won't help
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e  # transient: hang or dropped connection — retry once
    raise last_err


def run_agent_ollama(model: str, messages: list[dict], workspace: str, run_id: str,
                     approve: Callable, depth: int = 0, system_base: str | None = None) -> Iterator[dict]:
    system = ((system_base or AGENT_SYSTEM) + _vault_note()
              + tools.vault_lookup(_vault_query(messages)) + _project_instructions(workspace))
    msgs = [{"role": "system", "content": system}] + messages
    for step in range(MAX_STEPS):
        yield {"type": "stage", "stage": "thinking", "model": model, "step": step + 1}
        _manage_context(msgs)   # keep long runs inside the context window
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
                        approve: Callable, depth: int = 0, system_base: str | None = None) -> Iterator[dict]:
    import anthropic

    client = anthropic.Anthropic()
    system = ((system_base or AGENT_SYSTEM) + _vault_note()
              + tools.vault_lookup(_vault_query(messages)) + _project_instructions(workspace))
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
                     approve: Callable, depth: int = 0, system_base: str | None = None) -> Iterator[dict]:
    system = ((system_base or AGENT_SYSTEM) + _vault_note()
              + tools.vault_lookup(_vault_query(messages)) + _project_instructions(workspace))
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
                    approve: Callable, depth: int = 0, system_base: str | None = None) -> Iterator[dict]:
    remote = llm.remote_provider_for(model)
    if llm.is_api_model(model):
        return run_agent_anthropic(model, messages, workspace, run_id, approve, depth, system_base)
    if remote:
        prov, real_id = remote
        key = __import__("os").environ.get(prov["api_key_env"])
        if not key:
            return iter([{"type": "final_text",
                          "answer": f"{prov['name']} needs {prov['api_key_env']} set to use agent mode."}])
        spec = next((m for m in prov["models"] if m["id"] == real_id), {})
        return run_agent_openai(prov["base_url"], real_id, key,
                                (spec.get("price_in", 0), spec.get("price_out", 0)),
                                messages, workspace, run_id, approve, depth, system_base)
    if model.startswith(llm.LMS_PREFIX):
        return run_agent_openai(llm.LMSTUDIO_URL, model[len(llm.LMS_PREFIX):], None, (0, 0),
                                messages, workspace, run_id, approve, depth, system_base)
    return run_agent_ollama(model, messages, workspace, run_id, approve, depth, system_base)


def _image_to_spec(image_b64: str, vision_model: str = "qwen2.5vl:7b") -> str:
    """Coders can't see, so turn an attached image into a detailed implementation spec
    using the local vision model. Enables 'build the UI in this screenshot' in Agent mode."""
    prompt = ("Describe this image in precise detail so a developer can reproduce it in "
              "code without seeing it. If it's a UI/mockup: the layout, every component, "
              "all visible text/labels, colors, and the likely behavior. If it's a diagram: "
              "the structure and relationships. If it's a screenshot with text/code/errors: "
              "transcribe the relevant text exactly. Be thorough and specific.")
    msgs = [{"role": "user", "content": prompt, "images": [image_b64]}]
    out = ""
    try:
        for ev in llm.stream_chat(vision_model, msgs):
            if ev.get("type") == "delta":
                out += ev["text"]
    except Exception as e:
        return f"(the vision model could not read the image: {type(e).__name__}: {e})"
    return out.strip()


def _inject_image_spec(messages: list[dict], image_b64: str | None) -> list[dict]:
    """Prepend a vision-derived spec of the attached image to the user's request so the
    (blind) coder can build from it."""
    if not image_b64:
        return messages
    spec = _image_to_spec(image_b64)
    note = ("The user attached an image. A vision model read it — build from this "
            f"description:\n<image_description>\n{spec}\n</image_description>\n\n")
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):   # prepend to the LAST user message
        if out[i].get("role") == "user":
            out[i]["content"] = note + str(out[i].get("content", ""))
            break
    else:
        out.insert(0, {"role": "user", "content": note})
    return out


def run_agent(model: str, messages: list[dict], workspace: str,
              approve: Callable[[str, dict], bool] = lambda n, a: True,
              system_base: str | None = None, image_b64: str | None = None) -> Iterator[dict]:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    yield {"type": "run_started", "run_id": run_id}
    _ACTIVE_MODEL["name"] = model
    if image_b64:   # build-from-screenshot: vision model -> spec -> the (blind) coder
        yield {"type": "stage", "stage": "reading image", "model": "qwen2.5vl:7b", "round": 0}
        messages = _inject_image_spec(messages, image_b64)
    gen = _dispatch_agent(model, messages, workspace, run_id, approve, depth=0, system_base=system_base)
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


def run_prompt_maker(model: str, messages: list[dict], workspace: str,
                     approve: Callable[[str, dict], bool] = lambda n, a: True) -> Iterator[dict]:
    """Interactive prompt-engineering turn: the model interviews the user (with
    read-only research tools) and eventually emits a finished build prompt. Same event
    contract as run_agent, but scoped to research tools and the Prompt Maker persona."""
    prev_scope = tools.SCOPE
    tools.SCOPE = tools.RESEARCH_TOOLS
    try:
        yield from run_agent(model, messages, workspace, approve,
                             system_base=PROMPT_MAKER_SYSTEM)
    finally:
        tools.SCOPE = prev_scope


# Big enough that whole multi-file builds fit — a too-small cap truncates real code in
# the review payload and the reviewer wrongly reports the CODE as 'truncated/incomplete'
# (a false REVISE that cost an Opus chess build a pass). Any truncation is marked as
# Anvil's payload limit so the reviewer never mistakes it for a defect.
_REVIEW_CAP = 80000
_TRUNCATED = ("\n# [... this file is longer; the rest was trimmed to fit Anvil's review "
              "payload. This trim is NOT a code defect — do not flag it as incomplete ...]")


def _gather_built_files(workspace: str, paths: set[str], cap: int = _REVIEW_CAP) -> str:
    """Concatenate the files the agent wrote/edited so the reviewer can inspect them."""
    ws = Path(workspace)
    chunks, total = [], 0
    for rel in sorted(paths):
        p = Path(rel) if Path(rel).is_absolute() else ws / rel
        try:
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        header = f"# ===== {rel} =====\n"
        if total + len(header) + 40 >= cap:
            chunks.append(f"# ===== {rel} (omitted — review payload full; not a defect) =====")
            continue
        avail = cap - total - len(header)
        body = text if len(text) <= avail else text[:avail] + _TRUNCATED
        chunks.append(header + body)
        total += len(header) + len(body)
    return "\n\n".join(chunks)


_FAIL_MARKERS = ("(agent stopped on error", "(agent error", "(agent hit the step limit",
                 "(request declined by safety", "timed out", "to use agent mode.")


def _agent_failed(answer: str) -> str | None:
    """If the agent's final text signals it did NOT finish cleanly, return a short
    reason (else None). A crashed or truncated build must never be reported as passed."""
    a = (answer or "").strip()
    if a.startswith("(agent ") or any(m in a for m in _FAIL_MARKERS):
        return a[:200]
    return None


def _file_manifest(workspace: str, paths: set[str]) -> str:
    ws = Path(workspace)
    items = []
    for rel in sorted(paths):
        p = Path(rel) if Path(rel).is_absolute() else ws / rel
        try:
            sz = p.stat().st_size if p.is_file() else 0
        except OSError:
            sz = 0
        items.append(f"{rel} ({sz}B)")
    return ", ".join(items) if items else "(none)"


def _exit_code(out: str) -> int | None:
    """Parse the leading '[exit N]' the bash tool prepends to its output."""
    if out.startswith("[exit "):
        try:
            return int(out[6:out.index("]")])
        except ValueError:
            return None
    return None


# Shell commands that constitute a build's verification (vs. exploratory debugging).
# We judge the build on the last of THESE, so trailing debug commands can't mask a
# red test (the exact hole the chess run exposed: failing unittest, then exit-0 pokes).
_TEST_HINTS = (
    # Python
    "unittest", "pytest", "py.test", "nose", "selftest", "discover", "test_", "tests/", "tests\\",
    # JavaScript / TypeScript
    "npm test", "npm run test", "yarn test", "pnpm test", "jest", "vitest", "mocha", "playwright test",
    # Rust / Go / C# / Java
    "cargo test", "go test", "dotnet test", "mvn test", "mvn verify", "gradle test",
    "gradlew test", "gradlew build", "gradle build",
    # C/C++ / Ruby / PHP
    "ctest", "make test", "make check", "rspec", "phpunit",
)


def _is_test_cmd(cmd: str) -> bool:
    c = (cmd or "").lower()
    return any(h in c for h in _TEST_HINTS)


def _review_input(workspace: str, written: set[str], files_text: str, test_note: str) -> str:
    """Wrap the built files with a completeness header + the build's own self-test
    result, so the reviewer judges the whole deliverable — not a lone stub, and not
    code that looks fine but does not actually run — against the request."""
    return (
        "[AUTONOMOUS BUILD — completeness review]\n"
        "The user expects a COMPLETE, RUNNABLE program that fully satisfies the request. "
        f"Files the build actually wrote: {_file_manifest(workspace, written)}.\n"
        f"Self-test: {test_note}\n"
        "If required functionality is missing, only stubbed, the program would not run "
        "end to end, or its self-test did not pass, the verdict MUST be 'revise' — never "
        "pass a skeleton, a lone requirements/config file, or code with a failing test.\n\n"
        f"----- ALL FILES PRODUCED -----\n{files_text}"
    )


def run_agent_reviewed(model: str, messages: list[dict], workspace: str,
                       approve: Callable[[str, dict], bool] = lambda n, a: True,
                       *, review: bool = True, reviewer: str = "claude-haiku-4-5",
                       auto_revise: bool = True, max_rounds: int = 2,
                       image_b64: str | None = None) -> Iterator[dict]:
    """Local agent build + a gated frontier review of the finished build.

    The local model builds with tools; when it's done a paid reviewer inspects the
    files it wrote and either passes it or returns concrete fixes, which are fed back
    into the agent for another build round. Fully automated — no human intervention.
    Degrades to a plain agent run when review is off or no API reviewer is configured.
    """
    reviewing = bool(review and reviewer in llm.API_MODELS)
    if image_b64:   # build-from-screenshot: describe once, then the coder builds from it
        messages = _inject_image_spec(messages, image_b64)
    conv = list(messages)
    user_request = next((m["content"] for m in messages if m.get("role") == "user"), "")
    total_cost = 0.0
    run_id = None
    passed = None
    revised = False
    last_answer = ""
    written: set[str] = set()

    for round_i in range(1, max_rounds + 1):
        # --- build (round 1) or fix (later rounds): run the agent to completion ---
        round_answer = ""
        last_call = None
        cur_is_test = False
        last_test = None  # (exit_code, output) of the build's most recent TEST/self-test run
        for ev in run_agent(model, conv, workspace, approve):
            et = ev.get("type")
            if et == "run_started":
                if run_id is None:
                    run_id = ev["run_id"]
                    yield ev
                continue  # swallow later run_starts; one run_id spans the rounds
            if et == "final":
                total_cost = round(total_cost + (ev.get("cost") or 0), 5)
                continue  # swallow inner finals; the outer final is emitted once, at the end
            if et == "final_text":
                round_answer = ev.get("answer") or round_answer
            if et == "tool_call":
                last_call = ev.get("name")
                if last_call in ("write_file", "edit_file"):
                    p = (ev.get("args") or {}).get("path")
                    if p:
                        written.add(p)
                elif last_call == "bash":
                    cur_is_test = _is_test_cmd((ev.get("args") or {}).get("command", ""))
            # Judge on the last TEST/self-test command, not the last shell command —
            # otherwise trailing debug pokes (exit 0) mask a red test.
            if et == "tool_result" and last_call == "bash" and cur_is_test:
                last_test = (_exit_code(ev.get("output") or ""), ev.get("output") or "")
            yield ev
        last_answer = round_answer or last_answer

        if not reviewing:
            break

        # A build is only 'done' if it finished cleanly AND its own self-test passed.
        # Reasons it is NOT done: a crash/timeout/step-limit final, or its last self-test
        # run exited non-zero. Such a build can never be 'passed'; retry with the failure
        # fed back if rounds remain, else fail.
        fail = _agent_failed(round_answer)
        test_failed = last_test is not None and last_test[0] not in (0, None)
        if fail or test_failed:
            passed = False
            reason = fail or ("its self-test failed:\n" + last_test[1][:800])
            if auto_revise and round_i < max_rounds:
                revised = True
                yield {"type": "review_error",
                       "error": f"build did not verify — retrying ({reason[:80]})"}
                conv = conv + [
                    {"role": "assistant", "content": round_answer or "(build did not finish)"},
                    {"role": "user", "content":
                     "Your build is NOT done — it did not pass its own check:\n" + reason +
                     "\n\nFix the code, then re-run your headless self-test until it exits 0 "
                     "before you stop. Do not claim success while the self-test fails."},
                ]
                continue
            break

        produced = _gather_built_files(workspace, written)
        if not produced.strip():
            passed = False   # build 'finished' but wrote nothing usable
            yield {"type": "review_error",
                   "error": "build produced no files — nothing to review (not passed)"}
            break

        test_note = ("the build ran no self-test — judge runnability from the code"
                     if last_test is None else "the build's self-test passed (exit 0)")
        yield {"type": "stage", "stage": "reviewing", "model": reviewer, "round": round_i}
        try:
            rev, rusage = llm.review_code(reviewer, user_request,
                                          _review_input(workspace, written, produced, test_note))
        except Exception as e:
            yield {"type": "review_error", "error": f"review failed: {type(e).__name__}: {e}"}
            break
        total_cost = round(total_cost + rusage.cost_usd, 5)
        passed = rev["verdict"] == "pass"
        yield {"type": "review", "round": round_i, "verdict": rev["verdict"],
               "summary": rev["summary"], "issues": rev["issues"],
               "reviewer": reviewer, "cost": round(rusage.cost_usd, 5)}

        if passed or not auto_revise or round_i == max_rounds:
            break
        # feed the reviewer's fixes back in for another build round
        revised = True
        issues_txt = "\n".join(f"- [{i['severity']}] {i['problem']} -> {i['fix']}"
                               for i in rev["issues"])
        conv = conv + [
            {"role": "assistant", "content": last_answer or "(build complete)"},
            {"role": "user", "content":
             "A senior reviewer checked your build and it needs fixes before it is done. "
             "Fix ALL of the issues below by editing the files, then re-run your headless "
             "self-test to confirm it still passes.\n\n"
             f"{rev['revision_instruction']}\n\nIssues:\n{issues_txt}"},
        ]

    yield {"type": "final", "cost": total_cost, "reviewed": reviewing,
           "revised": revised, "passed": passed, "answer": "", "run_id": run_id}


FIXER_SYSTEM = (
    "You are a senior quality-check engineer on Anvil. Another model just built the code "
    "in this workspace. Your job is NOT to rewrite it from scratch — INSPECT what is there "
    "and make targeted fixes so it fully works. Read the files, run the headless self-test "
    "to see the real state, then fix the issues in your assigned focus area by editing the "
    "files. Re-run the self-test until it exits 0. Keep edits minimal and surgical. If a "
    "self-test or tests do not exist yet, add a small headless one so the build is "
    "verifiable. When done, briefly state what you fixed, or that nothing needed fixing."
)

# Each checker sub-agent gets one focus so it reviews deeply instead of skimming.
DEFAULT_LENSES = [
    ("runs & complete",
     "make it actually run and be complete — fix any crash, import error, or failing "
     "self-test, and fill in anything missing, stubbed, or left as a TODO so it fully "
     "does what the user asked (no placeholders)."),
    ("correctness",
     "find and fix correctness bugs — wrong output, broken edge cases, or rules/logic "
     "implemented incorrectly — and prove the fix with the self-test."),
]


def run_agent_squad(model: str, messages: list[dict], workspace: str,
                    approve: Callable[[str, dict], bool] = lambda n, a: True, *,
                    checker_model: str | None = None, lenses: list | None = None,
                    review: bool = False, reviewer: str = "claude-haiku-4-5",
                    escalate_to: str | None = None,
                    image_b64: str | None = None) -> Iterator[dict]:
    """Main model builds; then a squad of quality-check sub-agents inspect the code and
    directly FIX what they find (each with a focused lens), re-testing as they go —
    exactly 'main model writes, sub-agents look through and fill in / fix'. The checker
    can be the same local model (free extra passes with fresh context) or a stronger/paid
    one. If the free path still can't get the self-test green and `escalate_to` names a
    paid model, ONE last-mile fix pass runs with it (only then, only when failing) — free
    until it can't, then cents. An optional final paid review gives a verdict. Fully
    automated."""
    checker = checker_model or model
    lenses = DEFAULT_LENSES if lenses is None else lenses
    if image_b64:   # build-from-screenshot: vision spec -> the coder + all fixers
        messages = _inject_image_spec(messages, image_b64)
    user_request = next((m["content"] for m in messages if m.get("role") == "user"), "")
    st = {"run_id": None, "cost": 0.0, "written": set(), "last_test": None}

    def drive(mdl, msgs, system_base):
        """Run one agent pass, streaming its events and capturing build state."""
        last_call, cur_is_test = None, False
        st["last_test"] = None  # per-pass; the squad judges on the latest pass's test
        for ev in run_agent(mdl, msgs, workspace, approve, system_base=system_base):
            et = ev.get("type")
            if et == "run_started":
                if st["run_id"] is None:
                    st["run_id"] = ev["run_id"]
                    yield ev
                continue
            if et == "final":
                st["cost"] = round(st["cost"] + (ev.get("cost") or 0), 5)
                continue
            if et == "tool_call":
                last_call = ev.get("name")
                if last_call in ("write_file", "edit_file"):
                    p = (ev.get("args") or {}).get("path")
                    if p:
                        st["written"].add(p)
                elif last_call == "bash":
                    cur_is_test = _is_test_cmd((ev.get("args") or {}).get("command", ""))
            if et == "tool_result" and last_call == "bash" and cur_is_test:
                st["last_test"] = (_exit_code(ev.get("output") or ""), ev.get("output") or "")
            yield ev

    # 1) main build
    yield {"type": "stage", "stage": "building", "model": model, "round": 0}
    yield from drive(model, list(messages), None)

    # 2) quality-check squad — each sub-agent inspects and fixes directly
    for key, lens in lenses:
        if not st["written"]:
            break  # nothing was built; no point checking
        yield {"type": "stage", "stage": f"quality-check: {key}", "model": checker, "round": 0}
        fixer_msg = [{"role": "user", "content":
                      "Another model built a project in this workspace for this request:\n\n"
                      f"<request>\n{user_request}\n</request>\n\n"
                      f"Inspect what is there and fix issues in this focus area — {lens}\n"
                      "Make targeted edits (do not rewrite from scratch), then run the "
                      "headless self-test to confirm it passes."}]
        yield from drive(checker, fixer_msg, FIXER_SYSTEM)

    # 2b) AUTO-ESCALATION — the free/local squad couldn't get the self-test green, so pay
    # for JUST the last-mile fix with a stronger model. Only fires when it's actually
    # failing, so you stay free until the local path genuinely can't finish.
    lt = st["last_test"]
    if (lt is not None and lt[0] not in (0, None) and escalate_to
            and escalate_to in llm.API_MODELS and escalate_to != checker and st["written"]):
        yield {"type": "stage", "stage": f"escalate: paid fix ({escalate_to})",
               "model": escalate_to, "round": 0}
        esc_msg = [{"role": "user", "content":
                    "Another model built a project in this workspace for this request:\n\n"
                    f"<request>\n{user_request}\n</request>\n\n"
                    "Its headless self-test is still FAILING with:\n"
                    f"{lt[1][:800]}\n\n"
                    "Diagnose and fix ALL the bugs with targeted edits (do not rewrite from "
                    "scratch), then re-run the self-test until it exits 0."}]
        yield from drive(escalate_to, esc_msg, FIXER_SYSTEM)

    # 3) verdict from the final self-test, plus an optional paid review
    lt = st["last_test"]
    passed = None if lt is None else (lt[0] == 0)
    if review and reviewer in llm.API_MODELS and st["written"]:
        produced = _gather_built_files(workspace, st["written"])
        if produced.strip():
            note = ("the build's self-test passed (exit 0)" if passed else
                    "the self-test is FAILING" if passed is False else "no self-test detected")
            yield {"type": "stage", "stage": "reviewing", "model": reviewer, "round": 1}
            try:
                rev, rusage = llm.review_code(reviewer, user_request,
                                              _review_input(workspace, st["written"], produced, note))
                st["cost"] = round(st["cost"] + rusage.cost_usd, 5)
                yield {"type": "review", "round": 1, "verdict": rev["verdict"],
                       "summary": rev["summary"], "issues": rev["issues"],
                       "reviewer": reviewer, "cost": round(rusage.cost_usd, 5)}
                if rev["verdict"] != "pass":
                    passed = False
            except Exception as e:
                yield {"type": "review_error", "error": f"review failed: {type(e).__name__}: {e}"}

    yield {"type": "final", "cost": st["cost"], "reviewed": bool(review),
           "revised": True, "passed": passed, "answer": "", "run_id": st["run_id"]}
