"""Anvil agent tools — the Claude Code / Cursor tool surface, local-first.

Every tool takes a workspace root; file paths are confined to it (traversal
outside the workspace is rejected). `bash` runs through the system shell with
a timeout. Web tools give local models the same internet access Claude has.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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
    {"name": "visual_check",
     "description": "Look at an image in the workspace (a rendered game frame or UI screenshot) "
                    "with a local vision model and report whether it looks correct. A headless "
                    "self-test only proves a graphical program RUNS — this proves it LOOKS right. "
                    "Save a frame first (pygame.image.save(screen,'frame.png') / Panda3D "
                    "screenshot), then visual_check it.",
     "parameters": {"type": "object", "properties": {
         "image": {"type": "string", "description": "Relative path to the image in the workspace"},
         "expectation": {"type": "string",
                         "description": "What it should show, e.g. 'a 3D maze with walls and a HUD'"}},
         "required": ["image", "expectation"]}},
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

# The coding playbook shipped WITH Anvil — always searched for RAG so every user gets the
# reference patterns out of the box, on top of their own vault. Lives at repo_root/playbook
# in dev, and inside the PyInstaller bundle (_MEIPASS/playbook) in the packaged .exe.
def _find_playbook() -> str | None:
    cands = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        cands.append(Path(sys._MEIPASS) / "playbook")
    cands.append(Path(__file__).parent.parent / "playbook")
    for c in cands:
        if c.is_dir():
            return str(c)
    return None


PLAYBOOK_PATH: str | None = _find_playbook()


_LAST_VAULT_LOOKUP: list[str] = []   # note names injected by the most recent vault_lookup
_VAULT_STOP = {"and", "the", "for", "with", "you", "are", "that", "this", "have", "make",
               "want", "from", "into", "your", "get", "its", "can", "will", "would",
               "just", "like", "some", "any", "them", "there", "when", "what", "how"}


def _keyword_notes(root: str, terms: list, k: int) -> list:
    """Keyword-score .md notes under `root`; return top-k [(stem, body)] scoring >= 4."""
    scored = []
    for md in Path(root).rglob("*.md"):
        if ".obsidian" in md.parts or ".trash" in md.parts:
            continue
        try:
            body = md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        score = sum((md.stem + "\n" + body).lower().count(t) for t in terms)
        if score >= 4:
            scored.append((score, md.stem, body))
    scored.sort(reverse=True)
    return [(stem, body) for _, stem, body in scored[:k]]


_PB_VEC: dict = {}   # cached playbook embeddings: {"sig", "notes":[{stem,body,vec}]}


def _playbook_semantic(query: str, k: int, floor: float = 0.45) -> list | None:
    """Semantic top-k over the bundled playbook via nomic-embed (cached to
    playbook/.rag_vectors.json). Returns [(stem, body)] by cosine >= floor, or None when
    embeddings aren't available (Ollama/nomic down) so the caller falls back to keyword."""
    if not PLAYBOOK_PATH:
        return None
    notes = []
    for md in Path(PLAYBOOK_PATH).rglob("*.md"):
        if ".obsidian" in md.parts:
            continue
        try:
            notes.append((md.stem, md.read_text(encoding="utf-8", errors="replace")))
        except Exception:
            continue
    if not notes:
        return None
    sig = hashlib.md5(("|".join(sorted(s for s, _ in notes))
                       + str(sum(len(b) for _, b in notes))).encode()).hexdigest()
    cache_f = Path.home() / ".anvil" / "rag_vectors.json"   # writable in dev AND the .exe
    vecs = _PB_VEC["notes"] if _PB_VEC.get("sig") == sig else None
    if vecs is None and cache_f.exists():
        try:
            data = json.loads(cache_f.read_text())
            if data.get("sig") == sig:
                vecs = data["notes"]; _PB_VEC.update(data)
        except Exception:
            pass
    try:
        import semindex
        if vecs is None:                       # (re)build + cache the embeddings once
            vecs = [{"stem": s, "body": b, "vec": semindex._embed([f"{s}\n{b[:800]}"])[0]}
                    for s, b in notes]
            _PB_VEC.update({"sig": sig, "notes": vecs})
            try:
                cache_f.parent.mkdir(parents=True, exist_ok=True)
                cache_f.write_text(json.dumps({"sig": sig, "notes": vecs}))
            except Exception:
                pass
        qv = semindex._embed([query])[0]
        ranked = sorted(((semindex._cosine(qv, n["vec"]), n["stem"], n["body"]) for n in vecs),
                        reverse=True)
    except Exception:
        return None                            # embeddings unavailable -> keyword fallback
    return [(stem, body) for sim, stem, body in ranked if sim >= floor][:k]


def _format_rag(pairs: list, cap: int) -> str:
    out, total = [], 0
    for stem, body in pairs:
        if total >= cap:
            break
        chunk = body[: cap - total]
        out.append(f"### {stem}\n{chunk}")
        total += len(chunk)
        _LAST_VAULT_LOOKUP.append(stem)
    if not out:
        return ""
    return ("\n\nReference notes auto-retrieved from the knowledge vault for this task — use "
            "these correct patterns instead of guessing or re-deriving the API:\n\n"
            + "\n\n".join(out))


def vault_lookup(query: str, k: int = 2, cap: int = 6000) -> str:
    """Proactive RAG: full text of the top-k reference notes for `query`, injected into the
    agent's system prompt so the model has the pattern in context without having to search.
    Semantic (nomic-embed) over the bundled playbook when available, keyword otherwise and
    for the user's own vault. '' when nothing clearly matches (won't inject noise)."""
    _LAST_VAULT_LOOKUP.clear()
    terms = [t for t in query.lower().split() if len(t) > 2 and t not in _VAULT_STOP]
    if not terms:
        return ""
    pairs, seen = [], set()
    sem = _playbook_semantic(query, k)
    pb = sem if sem is not None else (_keyword_notes(PLAYBOOK_PATH, terms, k) if PLAYBOOK_PATH else [])
    for stem, body in pb + (_keyword_notes(VAULT_PATH, terms, k)
                            if VAULT_PATH and VAULT_PATH != PLAYBOOK_PATH else []):
        if stem not in seen:
            seen.add(stem); pairs.append((stem, body))
    return _format_rag(pairs[:k], cap)


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


def _visual_check(image_rel: str, expectation: str, root: Path) -> str:
    """Send a workspace image (a rendered frame / screenshot) to the local vision model and
    report whether it LOOKS right — beyond a headless self-test proving it merely runs."""
    import base64
    try:
        p = _safe(root, image_rel)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.is_file():
        return f"ERROR: image not found: {image_rel} (save a frame first, e.g. pygame.image.save)"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode()
    except Exception as e:
        return f"ERROR: couldn't read image: {e}"
    prompt = (f"Does this image show a working {expectation}? Describe what you actually see. "
              "Explicitly flag any problem: a blank/black screen, an error dialog, garbled or "
              "overlapping graphics, or missing elements. If it looks correct, say so clearly.")
    try:
        import llm
        r = requests.post(f"{llm.OLLAMA_URL}/api/chat", json={
            "model": "qwen2.5vl:7b", "stream": False,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "options": {"num_predict": 250, "temperature": 0}}, timeout=180)
        r.raise_for_status()
        return "[visual check] " + r.json()["message"]["content"].strip()
    except Exception as e:
        return f"[visual check unavailable: {type(e).__name__}: {e}]"


# tools that modify state or execute code -> may require user approval
DANGEROUS = {"write_file", "edit_file", "bash", "vault_write"}

# Read-only research tools — the set Prompt Maker is scoped to (it must not build).
RESEARCH_TOOLS = {"list_dir", "read_file", "web_search", "web_fetch",
                  "codebase_search", "vault_search", "vault_read"}

# When set to a set of tool names, only those built-ins are exposed to the model.
# Used to give Prompt Maker research-only tools without touching the agent runners.
SCOPE: set[str] | None = None


def _active_specs() -> list[dict]:
    import mcp_client
    base = [t for t in TOOL_SPECS if t["name"] != "codebase_search" or INDEX_READY]
    specs = base + (VAULT_SPECS if VAULT_PATH else []) + mcp_client.specs()
    if SCOPE is not None:
        specs = [t for t in specs if t["name"] in SCOPE]
    return specs


def is_dangerous(name: str) -> bool:
    """State-changing built-ins plus every MCP tool (external side effects unknown)."""
    return name in DANGEROUS or name.startswith("mcp_")


def ollama_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in _active_specs()]


def anthropic_tools() -> list[dict]:
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]} for t in _active_specs()]


# ---------------- implementations ----------------

def _posix_shell() -> str | None:
    """Locate a POSIX shell (git-bash on Windows) so the agent's bash-style commands
    — heredocs, `$(...)`, POSIX quoting — actually work. Without this, Windows runs
    them through cmd.exe and every heredoc/pipe idiom the model writes fails."""
    if sys.platform != "win32":
        return None  # shell=True already uses /bin/sh on POSIX
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(p).is_file():
            return p
    exe = shutil.which("bash")
    # skip the System32 WSL launcher — it shells into a whole other distro
    if exe and "System32" not in exe and "system32" not in exe:
        return exe
    return None


# Catastrophic commands the agent should NEVER run — a safety net on top of permission
# modes. Targets whole-disk / root / home wipes and machine control, NOT normal cleanup
# (rm -rf build, rm -rf node_modules stay allowed — they're relative to the workspace).
_CATASTROPHIC = [
    r"rm\s+-[rfd]{1,3}\s+(/|/\*|~|~/\*|\$HOME|/etc|/usr|/bin|/sbin|/var|/lib|/boot|/root|/System)(\s|$|/|\*)",
    r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",           # fork bomb
    r"\bmkfs(\.|\s)", r"\bdd\b[^|]*\bof=/dev/", r">\s*/dev/(sd|nvme|disk|hd)",
    r"\bformat\s+[a-zA-Z]:", r"\bdel\s+/[sqf]\b[^|]*[a-zA-Z]:\\", r"\brd\s+/s\b[^|]*[a-zA-Z]:",
    r"\b(shutdown|reboot|poweroff|halt|init\s+0)\b",
    r"Remove-Item[^|]*-Recurse[^|]*(C:\\|\$HOME|~|/)",
    r"\bchmod\s+-R\s+0?00\s+/",
]


def _is_catastrophic(command: str) -> str | None:
    for pat in _CATASTROPHIC:
        if re.search(pat, command, re.IGNORECASE):
            return pat
    return None


def _run_bash(command: str, root: Path, timeout: int) -> str:
    danger = _is_catastrophic(command)
    if danger:
        return ("[BLOCKED by Anvil safety] this command looks catastrophic (whole-disk / root / "
                "home wipe or machine control) and was refused. Work inside the workspace; if you "
                "genuinely need this, the user must run it themselves.")
    return _run_bash_impl(command, root, timeout)


def _find_jdk() -> str | None:
    """Locate a JDK that is installed but may not be on PATH. A portable/manual JDK sets
    its JAVA_HOME/PATH at Windows *User* scope, which does NOT propagate into an already-
    running process tree — so the agent shell would hit 'javac: command not found' even
    though the JDK is right there. Check JAVA_HOME, then a portable install under ~/tools."""
    exe = "javac.exe" if sys.platform == "win32" else "javac"
    jh = os.environ.get("JAVA_HOME")
    if jh and (Path(jh) / "bin" / exe).exists():
        return jh
    for c in sorted(Path.home().glob("tools/jdk-*"), reverse=True):  # newest first
        if (c / "bin" / exe).exists():
            return str(c)
    return None


_JDK = _find_jdk()  # resolved once at import


def _inject_toolchains(env: dict) -> None:
    """Make user-installed toolchains that live outside this process's PATH reachable by
    the agent shell. Today: a JDK whose User-scope env never propagated (see _find_jdk).
    Only injects when the tool isn't already reachable, so a real system install wins."""
    if _JDK and not shutil.which("javac", path=env.get("PATH")):
        env["JAVA_HOME"] = _JDK
        env["PATH"] = str(Path(_JDK) / "bin") + os.pathsep + env.get("PATH", "")


def _run_bash_impl(command: str, root: Path, timeout: int) -> str:
    """Run a shell command with guards learned from live testing:
      1. Use a real POSIX shell (git-bash) on Windows so bash-style commands work,
         instead of cmd.exe silently choking on heredocs and POSIX syntax.
      2. Force GUI toolkits headless (SDL/Qt offscreen) so a windowed program
         renders without opening a blocking window.
      3. Put user-installed toolchains (a portable JDK) on PATH so Java builds work
         even though their User-scope env vars never reached this process.
      4. Hard-kill the whole process tree on timeout — plain subprocess timeout
         on Windows kills the shell but orphans GUI children (and their windows).
    """
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")      # pygame/SDL: no window
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")  # Qt: no window
    env["PYTHONUNBUFFERED"] = "1"
    _inject_toolchains(env)                          # portable JDK -> PATH (Java builds)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # Windows only
    bash = _posix_shell()
    args = [bash, "-c", command] if bash else command
    proc = subprocess.Popen(args, shell=(bash is None), cwd=str(root), env=env,
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

    if name == "visual_check":
        return _visual_check(a["image"], a.get("expectation", "the described program"), root)

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
