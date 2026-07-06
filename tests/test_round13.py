"""Round 13 — proactive RAG (tools.vault_lookup + agent injection).

The vault-first nudge wasn't enough (gpt-oss:20b still web-searched). So Anvil now
searches the vault itself and injects the top note into the system prompt.
Run: py -3.14 -X utf8 tests/test_round13.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import tools  # noqa: E402
import agent  # noqa: E402


def _make_vault():
    v = Path(tempfile.mkdtemp())
    (v / ".obsidian").mkdir()
    (v / ".obsidian" / "app.json").write_text("{}")
    (v / "Panda3D walking sim.md").write_text(
        "# Panda3D walking sim\nUse BulletWorld for physics, gravity, collision, and NPCs "
        "in a first person 3d walking simulator. Set window-type offscreen for the selftest.")
    (v / "Flask app.md").write_text("# Flask app\nRoutes and SQLite database for a website.")
    (v / "Personal diary.md").write_text("# Diary\nToday I went for a walk and had lunch.")
    return v


def test_lookup_returns_relevant_note():
    def body():
        v = _make_vault()
        old = tools.VAULT_PATH
        tools.VAULT_PATH = str(v)
        try:
            out = tools.vault_lookup("build a 3d first person walking simulator with physics and npcs")
        finally:
            tools.VAULT_PATH = old
        expect("BulletWorld" in out, "injects the Panda3D note body")
        expect("Panda3D walking sim" in tools._LAST_VAULT_LOOKUP, "records which note was injected")
        expect("Diary" not in out, "irrelevant personal note is not injected")
    check("rag: vault_lookup returns the relevant note for the task", body)


def test_lookup_empty_when_no_match_or_no_vault():
    def body():
        v = _make_vault()
        old = tools.VAULT_PATH
        # no vault configured -> nothing
        tools.VAULT_PATH = None
        expect(tools.vault_lookup("anything") == "", "no vault -> empty")
        # vault set but query matches nothing relevant -> empty (below score threshold)
        tools.VAULT_PATH = str(v)
        try:
            out = tools.vault_lookup("quantum chromodynamics lattice gauge")
        finally:
            tools.VAULT_PATH = old
        expect(out == "", "no clear match -> empty (don't inject noise)")
    check("rag: empty when no vault or no clear match", body)


def test_injected_into_system_prompt():
    def body():
        v = _make_vault()
        old = tools.VAULT_PATH
        tools.VAULT_PATH = str(v)
        try:
            q = _q = agent._vault_query([{"role": "user", "content": "make a 3d walking simulator with physics"}])
            block = tools.vault_lookup(q)
        finally:
            tools.VAULT_PATH = old
        expect("physics" in q, "vault query is drawn from the user message")
        expect("BulletWorld" in block, "the retrieved note would land in the system prompt")
    check("rag: query from messages -> note injected into prompt", body)


if __name__ == "__main__":
    print("== relevant note =="); test_lookup_returns_relevant_note()
    print("== empty cases =="); test_lookup_empty_when_no_match_or_no_vault()
    print("== injection =="); test_injected_into_system_prompt()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
