"""Round 9 — Prompt Maker mode (run_prompt_maker + extract_build_prompt).

The model interviews the user with read-only research tools and emits a finished
build prompt between markers. Run: py -3.14 -X utf8 tests/test_round9.py
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

import agent  # noqa: E402
import tools  # noqa: E402


def test_extract_build_prompt():
    def body():
        good = ("Sounds great! Here it is:\n"
                "===BUILD PROMPT===\n"
                "Build a 2D solo asteroids game in Python with pygame. Ship rotates, "
                "asteroids split, keep score. Self-test headless before saying done.\n"
                "===END BUILD PROMPT===\n"
                "Send it to the builder or ask me to tweak it.")
        got = agent.extract_build_prompt(good)
        expect(got is not None and got.startswith("Build a 2D solo asteroids"),
               "extracts the prompt body")
        expect("===" not in got, "markers are stripped out")
        expect(agent.extract_build_prompt("just a normal question back to you?") is None,
               "no marker -> None")
        # tolerate a missing end marker (model truncation)
        no_end = "===BUILD PROMPT===\nmake a snake game, self-test it."
        expect(agent.extract_build_prompt(no_end).startswith("make a snake"),
               "works without the end marker too")
    check("prompt-maker: extract_build_prompt", body)


def test_scope_is_research_only():
    def body():
        prev = tools.SCOPE
        tools.SCOPE = tools.RESEARCH_TOOLS
        try:
            names = {t["name"] for t in tools._active_specs()}
        finally:
            tools.SCOPE = prev
        expect("web_search" in names, "research tools are exposed")
        expect("write_file" not in names, "no file writing while prompt-making")
        expect("bash" not in names, "no shell while prompt-making")
        expect(names <= tools.RESEARCH_TOOLS, "only research tools exposed under scope")
    check("prompt-maker: research-only tool scope", body)


def test_run_prompt_maker_scopes_and_restores():
    def body():
        captured = {}

        def fake_run_agent(model, messages, workspace, approve=lambda n, a: True,
                           system_base=None):
            captured["scope_during"] = tools.SCOPE
            captured["system"] = system_base
            yield {"type": "run_started", "run_id": "rid"}
            yield {"type": "final_text", "answer": "what kind of game — 2D or 3D?"}
            yield {"type": "final", "cost": 0.0, "reviewed": False, "revised": False,
                   "passed": None, "answer": "", "run_id": "rid"}

        real = agent.run_agent
        before = tools.SCOPE
        agent.run_agent = fake_run_agent
        try:
            evs = list(agent.run_prompt_maker(
                "m", [{"role": "user", "content": "build me a game"}], tempfile.mkdtemp()))
        finally:
            agent.run_agent = real
        expect(captured["scope_during"] == tools.RESEARCH_TOOLS,
               "tools are scoped to research during the run")
        expect(captured["system"] == agent.PROMPT_MAKER_SYSTEM,
               "the Prompt Maker persona is used")
        expect(tools.SCOPE == before, "scope is restored after the run")
        expect(evs[-1]["type"] == "final", "same event contract as run_agent")
        expect(any(e["type"] == "final_text" for e in evs), "asks the user a question")
    check("prompt-maker: run_prompt_maker scopes tools + restores", body)


if __name__ == "__main__":
    print("== extract =="); test_extract_build_prompt()
    print("== scope =="); test_scope_is_research_only()
    print("== run + restore =="); test_run_prompt_maker_scopes_and_restores()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
