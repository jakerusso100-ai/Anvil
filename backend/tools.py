"""Anvil agent tools — the Claude Code / Cursor tool surface, local-first.

Every tool takes a workspace root; file paths are confined to it (traversal
outside the workspace is rejected). `bash` runs through the system shell with
a timeout. Web tools give local models the same internet access Claude has.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

MAX_READ = 100_000
MAX_TOOL_RESULT = 30_000


# ---------------- schemas (OpenAI/Ollama style; converted for Anthropic) ----------------

TOOL_SPECS = [
    {"name": "list_dir",
     "description": "List files and folders at a relative path inside the workspace ('' = root).",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Relative path, empty for workspace root"}},
         "required": []}},
    {"name": "read_file",
     "description": "Read a text file from the workspace. Returns contents with line numbers.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file",
     "description": "Create or overwrite a file in the workspace with the given content.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]}},
    {"name": "edit_file",
     "description": "Replace an exact text snippet in a file. old_text must appear exactly once.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
         "required": ["path", "old_text", "new_text"]}},
    {"name": "bash",
     "description": "Run a shell command in the workspace (Windows). Returns stdout+stderr. "
                    "Use for running code, tests, pip installs, git.",
     "parameters": {"type": "object", "properties": {
         "command": {"type": "string"}, "timeout_sec": {"type": "integer", "description": "default 60"}},
         "required": ["command"]}},
    {"name": "web_search",
     "description": "Search the web. Returns titles, URLs and snippets.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}, "max_results": {"type": "integer", "description": "default 5"}},
         "required": ["query"]}},
    {"name": "web_fetch",
     "description": "Fetch a URL and return its text content (HTML stripped, truncated).",
     "parameters": {"type": "object", "properties": {
         "url": {"type": "string"}}, "required": ["url"]}},
    {"name": "codebase_search",
     "description": "Semantic search across the whole codebase by MEANING (not keywords). "
                    "Finds the most relevant code chunks for a natural-language query — use "
                    "this to locate where functionality lives before reading files.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "remember",
     "description": "Save a durable learning about THIS project (build/test/run commands, "
                    "conventions, gotchas, where things live, fixes that worked). Saved notes "
                    "are automatically loaded into your context in future sessions. Use when you "
                    "discover something worth not re-deriving next time.",
     "parameters": {"type": "object", "properties": {
         "note": {"type": "string", "description": "one concise learning"}},
         "required": ["note"]}},
    {"name": "spawn_subagent",
     "description": "Delegate a focused, self-contained subtask to a fresh sub-agent that has "
                    "the same tools. It runs independently and returns a summary — use this to "
                    "keep your own context clean for big multi-part work (e.g. 'write tests for "
                    "module X', 'investigate why Y fails'). Give it a complete, standalone task.",
     "parameters": {"type": "object", "properties": {
         "task": {"type": "string", "description": "complete standalone instruction"}},
         "required": ["task"]}},
]

# codebase_search is only offered when an index exists (set by the UI)
INDEX_READY = False

VAULT_SPECS = [
    {"name": "vault_search",
     "description": "Search the user's Obsidian notes vault (their personal knowledge base). "
                    "Returns matching notes with snippets. Use when the task references the "
                    "user's notes, past decisions, projects, or personal knowledge.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "vault_read",
     "description": "Read a note from the Obsidian vault by its path or title.",
     "parameters": {"type": "object", "properties": {
         "note": {"type": "string", "description": "note path or title"}}, "required": ["note"]}},
    {"name": "vault_write",
     "description": "Create or append to a note in the Obsidian vault. Use mode 'append' to add "
                    "to an existing note, 'create' for a new one.",
     "parameters": {"type": "object", "properties": {
         "note": {"type": "string"}, "content": {"type": "string"},
         "mode": {"type": "string", "enum": ["create", "append"]}},
         "required": ["note", "content"]}},
]

# set by the UI (settings) — when set, vault tools are exposed to the agent
VAULT_PATH: str | None = None


def detect_vaults() -> list[str]:
    """Find Obsidian vaults (.obsidian markers) in common locations."""
    home = Path.home()
    roots = [home / "Documents", home / "OneDrive" / "Documentos",
             home / "OneDrive" / "Documents", home / "Desktop"]
    found = []
    for r in roots:
        if not r.exists():
            continue
        try:
            for marker in r.glob("*/.obsidian"):
                found.append(str(marker.parent))
            for marker in r.glob("*/*/.obsidian"):
                found.append(str(marker.parent))
        except Exception:
            continue
    return sorted(set(found))


# tools that modify state or execute code -> may require user approval
DANGEROUS = {"write_file", "edit_file", "bash", "vault_write"}


def _active_specs() -> list[dict]:
    import mcp_client
    base = [t for t in TOOL_SPECS if t["name"] != "codebase_search" or INDEX_READY]
    return base + (VAULT_SPECS if VAULT_PATH else []) + mcp_client.specs()


def is_dangerous(name: str) -> bool:
    """State-changing built-ins plus every MCP tool (external side effects unknown)."""
    return name in DANGEROUS or name.startswith("mcp_")


def ollama_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in _active_specs()]


def anthropic_tools() -> list[dict]:
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]} for t in _active_specs()]


# ---------------- implementations ----------------

def _run_bash(command: str, root: Path, timeout: int) -> str:
    """Run a shell command with two safety guards learned from live testing:
      1. Force GUI toolkits headless (SDL/Qt offscreen) so a windowed program
         renders without opening a blocking window.
      2. Hard-kill the whole process tree on timeout — plain subprocess timeout
         on Windows kills the shell but orphans GUI children (and their windows).
    """
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")      # pygame/SDL: no window
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")  # Qt: no window
    env["PYTHONUNBUFFERED"] = "1"
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # Windows only
    proc = subprocess.Popen(command, shell=True, cwd=str(root), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            creationflags=flags)
    note = ""
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        rc = -1
        note = (f"\n[timed out after {timeout}s — process tree killed. If this was a GUI "
                f"program (game/window), it was run headless; give it a way to exit "
                f"(e.g. a --selftest/--frames flag or a QUIT after N frames) to test it.]")
    out = (stdout or "") + (("\n[stderr]\n" + stderr) if stderr else "")
    return f"[exit {rc}]\n{out.strip() or '(no output)'}{note}"


def _kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True)
    else:
        import signal as _sig
        try:
            os.killpg(os.getpgid(pid), _sig.SIGKILL)
        except Exception:
            pass


def _safe(root: Path, rel: str) -> Path:
    p = (root / (rel or "")).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise ValueError(f"path escapes workspace: {rel}")
    return p


def run_tool(name: str, args: dict, workspace: str) -> str:
    if name.startswith("mcp_"):
        import mcp_client
        return mcp_client.call(name, args or {})
    root = Path(workspace)
    try:
        out = _dispatch(name, args or {}, root)
    except Exception as e:
        out = f"ERROR: {type(e).__name__}: {e}"
    if len(out) > MAX_TOOL_RESULT:
        out = out[:MAX_TOOL_RESULT] + f"\n... [truncated, {len(out)} chars total]"
    return out


def _dispatch(name: str, a: dict, root: Path) -> str:
    if name == "list_dir":
        p = _safe(root, a.get("path", ""))
        if not p.exists():
            return f"not found: {a.get('path')}"
        rows = []
        for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            if child.name.startswith((".git", "__pycache__", "node_modules")):
                continue
            rows.append(f"{'[d]' if child.is_dir() else '   '} {child.relative_to(root)}")
        return "\n".join(rows[:400]) or "(empty)"

    if name == "read_file":
        p = _safe(root, a["path"])
        text = p.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
        return "\n".join(f"{i+1:5d}| {ln}" for i, ln in enumerate(text.splitlines()))

    if name == "write_file":
        p = _safe(root, a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"], encoding="utf-8")
        return f"wrote {len(a['content'])} chars to {a['path']}"

    if name == "edit_file":
        p = _safe(root, a["path"])
        text = p.read_text(encoding="utf-8")
        n = text.count(a["old_text"])
        if n == 0:
            return "ERROR: old_text not found in file"
        if n > 1:
            return f"ERROR: old_text appears {n} times; provide a more unique snippet"
        p.write_text(text.replace(a["old_text"], a["new_text"], 1), encoding="utf-8")
        return f"edited {a['path']}"

    if name == "bash":
        return _run_bash(a["command"], root, int(a.get("timeout_sec", 60)))

    if name == "web_search":
        from ddgs import DDGS
        results = DDGS().text(a["query"], max_results=int(a.get("max_results", 5)))
        return json.dumps([{"title": r.get("title"), "url": r.get("href"),
                            "snippet": r.get("body")} for r in results], indent=1)

    if name == "remember":
        mem = root / ".anvil" / "memory.md"
        mem.parent.mkdir(parents=True, exist_ok=True)
        import time as _t
        line = f"- ({_t.strftime('%Y-%m-%d')}) {a['note'].strip()}\n"
        existing = mem.read_text(encoding="utf-8") if mem.exists() else "# Project memory (auto)\n\n"
        if a["note"].strip() in existing:
            return "already remembered"
        mem.write_text(existing + line, encoding="utf-8")
        return "saved to project memory"

    if name == "codebase_search":
        import semindex
        hits = semindex.search(str(root), a["query"])
        if not hits:
            return "no semantic index yet (build it in Anvil) or no matches"
        return "\n\n".join(f"[{h['path']}:{h['start']}] (score {h['score']})\n{h['text']}"
                           for h in hits)

    if name == "vault_search":
        if not VAULT_PATH:
            return "ERROR: no Obsidian vault configured"
        vroot = Path(VAULT_PATH)
        terms = [t for t in a["query"].lower().split() if t]
        hits = []
        for md in vroot.rglob("*.md"):
            if ".obsidian" in md.parts or ".trash" in md.parts:
                continue
            try:
                body = md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            hay = (md.stem + "\n" + body).lower()
            score = sum(hay.count(t) for t in terms)
            if score:
                i = min((hay.find(t) for t in terms if t in hay), default=0)
                snippet = body[max(0, i - 60):i + 240].strip()
                hits.append((score, str(md.relative_to(vroot)), snippet))
        hits.sort(reverse=True)
        if not hits:
            return "no notes matched"
        return "\n\n".join(f"[{p}] (score {s})\n{sn}" for s, p, sn in hits[:6])

    if name == "vault_read":
        if not VAULT_PATH:
            return "ERROR: no Obsidian vault configured"
        vroot = Path(VAULT_PATH)
        want = a["note"].lower().removesuffix(".md")
        for md in vroot.rglob("*.md"):
            if ".obsidian" in md.parts:
                continue
            rel = str(md.relative_to(vroot)).lower().removesuffix(".md")
            if rel == want or md.stem.lower() == want:
                return md.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
        return f"ERROR: note not found: {a['note']}"

    if name == "vault_write":
        if not VAULT_PATH:
            return "ERROR: no Obsidian vault configured"
        vroot = Path(VAULT_PATH)
        rel = a["note"] if a["note"].endswith(".md") else a["note"] + ".md"
        p = (vroot / rel).resolve()
        if not str(p).startswith(str(vroot.resolve())):
            return "ERROR: note path escapes vault"
        p.parent.mkdir(parents=True, exist_ok=True)
        if a.get("mode", "create") == "append" and p.exists():
            p.write_text(p.read_text(encoding="utf-8", errors="replace")
                         + "\n" + a["content"], encoding="utf-8")
            return f"appended {len(a['content'])} chars to {rel}"
        p.write_text(a["content"], encoding="utf-8")
        return f"wrote note {rel}"

    if name == "web_fetch":
        import re
        r = requests.get(a["url"], timeout=20, headers={"User-Agent": "Mozilla/5.0 (Anvil)"})
        html = r.text
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text[:MAX_TOOL_RESULT]

    return f"ERROR: unknown tool {name}"
