"""Session persistence — conversations survive app restarts (Claude Code-style).

One JSON per session under ~/.anvil/sessions/. Auto-saved after every turn.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

SESS_DIR = Path.home() / ".anvil" / "sessions"
KEEP = 100


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def save(session_id: str, history: list[dict], workspace: str, cost: float = 0.0) -> None:
    if not history:
        return
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    first_user = next((m["content"] for m in history if m["role"] == "user"), "untitled")
    data = {
        "id": session_id,
        "title": first_user.strip().splitlines()[0][:70],
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "workspace": workspace,
        "cost": round(cost, 5),
        "history": history,
    }
    (SESS_DIR / f"{session_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    _prune()


def _prune() -> None:
    files = sorted(SESS_DIR.glob("*.json"), reverse=True)
    for old in files[KEEP:]:
        try:
            old.unlink()
        except Exception:
            pass


def list_sessions(limit: int = 30) -> list[dict]:
    if not SESS_DIR.exists():
        return []
    out = []
    for f in sorted(SESS_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": d["id"], "title": d.get("title", "untitled"),
                        "updated": d.get("updated", ""), "n": len(d.get("history", []))})
        except Exception:
            continue
    return out


def load(session_id: str) -> dict | None:
    f = SESS_DIR / f"{session_id}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
