"""Semantic index — embeddings-based search over code + Obsidian vault (Cursor's
"codebase understanding"). Local nomic-embed via Ollama; cached per workspace.

Index once (fast, chunked), then codebase_search finds relevant chunks by meaning,
not keywords. Cache lives at <workspace>/.anvil/semindex.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import requests

import llm

EMBED_MODEL = "nomic-embed-text:latest"
CHUNK_LINES = 40
CHUNK_OVERLAP = 8
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
            ".h", ".hpp", ".cs", ".rb", ".php", ".md", ".txt", ".json", ".yaml", ".yml",
            ".toml", ".sh", ".html", ".css"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".anvil", ".venv", "venv",
             "dist", "build", ".obsidian", ".trash"}
MAX_FILES = 600


def _embed(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        r = requests.post(f"{llm.OLLAMA_URL}/api/embeddings",
                          json={"model": EMBED_MODEL, "prompt": t[:6000]}, timeout=60)
        r.raise_for_status()
        out.append(r.json()["embedding"])
    return out


def _chunk_file(path: Path, rel: str) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    chunks = []
    i = 0
    step = CHUNK_LINES - CHUNK_OVERLAP
    while i < len(lines):
        body = "\n".join(lines[i:i + CHUNK_LINES]).strip()
        if body:
            chunks.append({"path": rel, "start": i + 1, "text": body})
        i += step
    return chunks


def _cache_path(workspace: str) -> Path:
    return Path(workspace) / ".anvil" / "semindex.json"


def _iter_files(workspace: str):
    root = Path(workspace)
    n = 0
    for p in root.rglob("*"):
        if n >= MAX_FILES:
            break
        if p.is_file() and p.suffix.lower() in CODE_EXT:
            if SKIP_DIRS & set(p.relative_to(root).parts):
                continue
            n += 1
            yield p, str(p.relative_to(root)).replace("\\", "/")


def build_index(workspace: str, extra_roots: list[str] | None = None,
                progress=None) -> dict:
    """Embed all code chunks (+ optional extra roots like a vault). Returns stats."""
    chunks: list[dict] = []
    for path, rel in _iter_files(workspace):
        chunks.extend(_chunk_file(path, rel))
    for extra in extra_roots or []:
        er = Path(extra)
        if not er.is_dir():
            continue
        cnt = 0
        for p in er.rglob("*.md"):
            if cnt >= 300 or (SKIP_DIRS & set(p.parts)):
                continue
            cnt += 1
            for c in _chunk_file(p, "vault:" + p.name):
                chunks.append(c)
    if not chunks:
        return {"chunks": 0, "error": "no indexable files"}
    # embed in batches with progress
    vecs = []
    for idx, c in enumerate(chunks):
        vecs.extend(_embed([c["text"]]))
        if progress and idx % 25 == 0:
            progress(idx, len(chunks))
    for c, v in zip(chunks, vecs):
        c["vec"] = v
    data = {"built": time.strftime("%Y-%m-%d %H:%M"), "model": EMBED_MODEL,
            "workspace": workspace, "chunks": chunks}
    cp = _cache_path(workspace)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(data), encoding="utf-8")
    return {"chunks": len(chunks), "built": data["built"]}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def load(workspace: str) -> dict | None:
    cp = _cache_path(workspace)
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text(encoding="utf-8"))
    except Exception:
        return None


def search(workspace: str, query: str, k: int = 6) -> list[dict]:
    data = load(workspace)
    if not data:
        return []
    qvec = _embed([query])[0]
    scored = [( _cosine(qvec, c["vec"]), c) for c in data["chunks"] if c.get("vec")]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"path": c["path"], "start": c["start"], "score": round(s, 3),
             "text": c["text"][:500]} for s, c in scored[:k]]


def status(workspace: str) -> dict:
    data = load(workspace)
    if not data:
        return {"indexed": False}
    return {"indexed": True, "chunks": len(data["chunks"]), "built": data.get("built")}
