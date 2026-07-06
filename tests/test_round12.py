"""Round 12 — quality-check squad (run_agent_squad).

Main model builds; checker sub-agents inspect and directly fix, each with a focused
lens; a verdict comes from the final self-test (+ optional paid review).
Run: py -3.14 -X utf8 tests/test_round12.py
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
import llm  # noqa: E402


def _builder(writes=True, test_exit=0):
    """Fake run_agent that records (model, system_base) per call and simulates a pass."""
    calls = []

    def fake(model, messages, workspace, approve=lambda n, a: True, system_base=None):
        calls.append((model, system_base))
        yield {"type": "run_started", "run_id": "rid"}
        if writes:
            Path(workspace, "game.py").write_text("def main():\n    return 1\n")
            yield {"type": "tool_call", "name": "write_file", "args": {"path": "game.py"}}
            yield {"type": "tool_result", "name": "write_file", "output": "ok"}
            yield {"type": "tool_call", "name": "bash",
                   "args": {"command": "python game.py --selftest"}}
            yield {"type": "tool_result", "name": "bash",
                   "output": f"[exit {test_exit}]\n{'OK' if test_exit == 0 else 'FAIL'}"}
        yield {"type": "final_text", "answer": "done"}
        yield {"type": "final", "cost": 0.001, "reviewed": False, "revised": False,
               "passed": None, "answer": "", "run_id": "rid"}

    return fake, calls


def test_build_then_fixer_squad():
    def body():
        ws = tempfile.mkdtemp()
        fake, calls = _builder(writes=True, test_exit=0)
        real = agent.run_agent
        agent.run_agent = fake
        try:
            evs = list(agent.run_agent_squad(
                "local-coder", [{"role": "user", "content": "build a game"}], ws,
                checker_model="checker-x", review=False))
        finally:
            agent.run_agent = real
        # 1 main build + 2 default lenses = 3 agent passes
        expect(len(calls) == 3, f"main build + 2 fixers = 3 passes, got {len(calls)}")
        expect(calls[0] == ("local-coder", None), "pass 1 is the main build (coder, default system)")
        expect(calls[1][0] == "checker-x" and calls[1][1] == agent.FIXER_SYSTEM,
               "fixers use the checker model + FIXER_SYSTEM persona")
        expect(calls[2][0] == "checker-x", "second fixer also uses the checker model")
        expect(evs[-1]["passed"] is True, "final self-test exit 0 -> passed")
        expect(any(e.get("stage", "").startswith("quality-check") for e in evs),
               "emits quality-check stage markers")
    check("squad: build then two fixer sub-agents run", body)


def test_squad_verdict_follows_last_selftest():
    def body():
        ws = tempfile.mkdtemp()
        # every pass leaves the self-test RED -> squad must not claim passed
        fake, _ = _builder(writes=True, test_exit=1)
        real = agent.run_agent
        agent.run_agent = fake
        try:
            evs = list(agent.run_agent_squad(
                "m", [{"role": "user", "content": "x"}], ws, checker_model="c", review=False))
        finally:
            agent.run_agent = real
        expect(evs[-1]["passed"] is False, "a still-red self-test after the squad -> not passed")
    check("squad: verdict follows the final self-test (red -> not passed)", body)


def test_empty_build_skips_squad():
    def body():
        ws = tempfile.mkdtemp()
        fake, calls = _builder(writes=False)  # main build writes nothing
        real = agent.run_agent
        agent.run_agent = fake
        try:
            evs = list(agent.run_agent_squad(
                "m", [{"role": "user", "content": "x"}], ws, checker_model="c", review=False))
        finally:
            agent.run_agent = real
        expect(len(calls) == 1, "no files built -> no fixer sub-agents run")
        expect(evs[-1]["passed"] is None, "nothing built -> passed is None (n/a)")
    check("squad: empty build skips the fixer squad", body)


def test_squad_optional_final_review():
    def body():
        ws = tempfile.mkdtemp()
        fake, _ = _builder(writes=True, test_exit=0)
        seen = {}

        def fake_review(reviewer, req, produced):
            seen["note_has_pass"] = "self-test passed" in produced
            return ({"verdict": "pass", "summary": "ok", "issues": [],
                     "revision_instruction": ""}, llm.Usage(1, 1, 0.002))

        real, rr = agent.run_agent, llm.review_code
        agent.run_agent, llm.review_code = fake, fake_review
        try:
            evs = list(agent.run_agent_squad(
                "m", [{"role": "user", "content": "x"}], ws,
                checker_model="c", review=True, reviewer="claude-haiku-4-5"))
        finally:
            agent.run_agent, llm.review_code = real, rr
        expect(any(e["type"] == "review" for e in evs), "optional final paid review runs")
        expect(seen.get("note_has_pass"), "the reviewer is told the self-test passed")
        expect(evs[-1]["cost"] >= 0.002, "review cost is included")
    check("squad: optional final paid review after the fixers", body)


if __name__ == "__main__":
    print("== build + fixers =="); test_build_then_fixer_squad()
    print("== verdict follows selftest =="); test_squad_verdict_follows_last_selftest()
    print("== empty skips squad =="); test_empty_build_skips_squad()
    print("== optional review =="); test_squad_optional_final_review()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
