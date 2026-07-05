"""Round 8 — agent-mode paid review + auto-fix loop (run_agent_reviewed).

The local model builds with tools; a paid reviewer then checks the finished build
and either passes it or loops concrete fixes back in — zero human intervention.
Run: py -3.14 -X utf8 tests/test_round8.py
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


def _fake_builder(files_by_round):
    """Fake run_agent that writes the given files (one dict of files per call)."""
    calls = {"n": 0}

    def fake_run_agent(model, messages, workspace, approve=lambda n, a: True):
        i = calls["n"]
        calls["n"] += 1
        spec = files_by_round[min(i, len(files_by_round) - 1)]
        for name, content in spec.items():
            Path(workspace, name).write_text(content, encoding="utf-8")
        yield {"type": "run_started", "run_id": "rid-1"}
        for name in spec:
            yield {"type": "tool_call", "name": "write_file", "args": {"path": name}}
            yield {"type": "tool_result", "output": "wrote " + name}
        yield {"type": "final_text", "answer": f"build round {i + 1} done"}
        yield {"type": "final", "cost": 0.002, "reviewed": False, "revised": False,
               "passed": None, "answer": "", "run_id": "rid-1"}

    return fake_run_agent, calls


def test_review_off_is_plain_build():
    def body():
        ws = tempfile.mkdtemp()
        fake, _ = _fake_builder([{"game.py": "def main():\n    return 1\n"}])
        real = agent.run_agent
        agent.run_agent = fake
        try:
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build"}], ws, review=False))
        finally:
            agent.run_agent = real
        expect(evs[-1]["type"] == "final", "ends on final")
        expect(evs[-1]["reviewed"] is False, "review off -> reviewed False")
        expect(not any(e["type"] == "review" for e in evs), "no review events when off")
    check("agent-review: off behaves like a plain build", body)


def test_review_pass_no_refix():
    def body():
        ws = tempfile.mkdtemp()
        fake, calls = _fake_builder([{"game.py": "def main():\n    return 1\n"}])
        seen = {}

        def fake_review(reviewer, req, produced):
            seen["produced"] = produced
            return ({"verdict": "pass", "summary": "correct", "issues": [],
                     "revision_instruction": ""}, llm.Usage(10, 5, 0.001))

        real, rr = agent.run_agent, llm.review_code
        agent.run_agent, llm.review_code = fake, fake_review
        try:
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build"}], ws,
                review=True, reviewer="claude-haiku-4-5", max_rounds=2))
        finally:
            agent.run_agent, llm.review_code = real, rr
        expect("game.py" in seen.get("produced", ""), "reviewer sees the built file")
        expect(evs[-1]["reviewed"] and evs[-1]["passed"], "reviewed + passed")
        expect(sum(1 for e in evs if e["type"] == "review") == 1, "exactly one review")
        expect(calls["n"] == 1, "pass -> no second build round")
        expect(evs[-1]["cost"] >= 0.002, "cost includes build + review")
    check("agent-review: pass verdict, no re-fix", body)


def test_review_revise_then_pass():
    def body():
        ws = tempfile.mkdtemp()
        fake, calls = _fake_builder([
            {"game.py": "def main():\n    pass  # buggy\n"},
            {"game.py": "def main():\n    return 1  # fixed\n"},
        ])
        seq = {"n": 0}

        def fake_review(reviewer, req, produced):
            seq["n"] += 1
            if seq["n"] == 1:
                return ({"verdict": "revise", "summary": "bug",
                         "issues": [{"severity": "major", "problem": "returns None",
                                     "fix": "return 1"}],
                         "revision_instruction": "make main return 1"},
                        llm.Usage(10, 5, 0.001))
            return ({"verdict": "pass", "summary": "fixed", "issues": [],
                     "revision_instruction": ""}, llm.Usage(10, 5, 0.001))

        real, rr = agent.run_agent, llm.review_code
        agent.run_agent, llm.review_code = fake, fake_review
        try:
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build"}], ws,
                review=True, reviewer="claude-haiku-4-5", auto_revise=True, max_rounds=2))
        finally:
            agent.run_agent, llm.review_code = real, rr
        expect(calls["n"] == 2, "revise -> a second build round ran")
        expect(sum(1 for e in evs if e["type"] == "review") == 2, "two review passes")
        expect(evs[-1]["revised"] and evs[-1]["passed"], "revised then passed")
        expect("fixed" in Path(ws, "game.py").read_text(), "the fix landed on disk")
    check("agent-review: revise -> auto-fix -> pass", body)


def test_local_reviewer_skips():
    def body():
        ws = tempfile.mkdtemp()
        fake, _ = _fake_builder([{"game.py": "def main():\n    return 1\n"}])
        real = agent.run_agent
        agent.run_agent = fake
        try:
            # a local (non-API) reviewer name must never trigger a paid review
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build"}], ws,
                review=True, reviewer="qwen3-coder-next:latest"))
        finally:
            agent.run_agent = real
        expect(evs[-1]["reviewed"] is False, "non-API reviewer -> no review")
        expect(not any(e["type"] == "review" for e in evs), "no review events")
    check("agent-review: local reviewer name is not billed", body)


def test_failed_build_never_passes():
    """A crashed / incomplete build must never be reported as passed, and must not be
    reviewed as if it finished (the bug the chess stress run exposed)."""
    def body():
        ws = tempfile.mkdtemp()

        def fake_run_agent(model, messages, workspace, approve=lambda n, a: True):
            Path(workspace, "requirements.txt").write_text("python-chess>=1.9")
            yield {"type": "run_started", "run_id": "rid"}
            yield {"type": "tool_call", "name": "write_file", "args": {"path": "requirements.txt"}}
            yield {"type": "tool_result", "output": "ok"}
            yield {"type": "final_text", "answer": "(agent stopped on error: HTTPError 500)"}
            yield {"type": "final", "cost": 0.001, "reviewed": False, "revised": False,
                   "passed": None, "answer": "", "run_id": "rid"}

        reviewed = {"n": 0}

        def fake_review(reviewer, req, produced):
            reviewed["n"] += 1
            return ({"verdict": "pass", "summary": "x", "issues": [],
                     "revision_instruction": ""}, llm.Usage(1, 1, 0.001))

        real, rr = agent.run_agent, llm.review_code
        agent.run_agent, llm.review_code = fake_run_agent, fake_review
        try:
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build chess"}], ws,
                review=True, reviewer="claude-haiku-4-5", max_rounds=1))
        finally:
            agent.run_agent, llm.review_code = real, rr
        expect(evs[-1]["passed"] is False, "a crashed build is never passed")
        expect(reviewed["n"] == 0, "a failed build is not sent to the reviewer")
        expect(not any(e["type"] == "review" for e in evs), "no review verdict emitted")
    check("agent-review: crashed build is never reported as passed", body)


def test_failed_build_retries_then_passes():
    """A failed first build is retried with the error fed back; if the retry finishes,
    the review runs on the completed build."""
    def body():
        ws = tempfile.mkdtemp()
        calls = {"n": 0}

        def fake_run_agent(model, messages, workspace, approve=lambda n, a: True):
            calls["n"] += 1
            yield {"type": "run_started", "run_id": "rid"}
            if calls["n"] == 1:
                Path(workspace, "requirements.txt").write_text("python-chess>=1.9")
                yield {"type": "final_text", "answer": "(agent stopped on error: boom)"}
            else:
                Path(workspace, "chess.py").write_text(
                    "import chess\ndef main():\n    return chess.Board()\n")
                yield {"type": "tool_call", "name": "write_file", "args": {"path": "chess.py"}}
                yield {"type": "final_text", "answer": "built the chess game, self-test passed"}
            yield {"type": "final", "cost": 0.001, "reviewed": False, "revised": False,
                   "passed": None, "answer": "", "run_id": "rid"}

        seen = {}

        def fake_review(reviewer, req, produced):
            seen["produced"] = produced
            return ({"verdict": "pass", "summary": "complete", "issues": [],
                     "revision_instruction": ""}, llm.Usage(1, 1, 0.001))

        real, rr = agent.run_agent, llm.review_code
        agent.run_agent, llm.review_code = fake_run_agent, fake_review
        try:
            evs = list(agent.run_agent_reviewed(
                "m", [{"role": "user", "content": "build chess"}], ws,
                review=True, reviewer="claude-haiku-4-5", auto_revise=True, max_rounds=2))
        finally:
            agent.run_agent, llm.review_code = real, rr
        expect(calls["n"] == 2, "the build was retried after the failure")
        expect("chess.py" in seen.get("produced", ""), "review runs on the completed retry")
        expect(evs[-1]["passed"] is True, "a retry that finishes + passes review passes")
        expect(evs[-1]["revised"] is True, "marked as revised (a retry happened)")
        expect(sum(1 for e in evs if e["type"] == "review") == 1, "review ran once, on the good build")
    check("agent-review: failed build retries with error fed back", body)


if __name__ == "__main__":
    print("== review off =="); test_review_off_is_plain_build()
    print("== review pass =="); test_review_pass_no_refix()
    print("== revise then pass =="); test_review_revise_then_pass()
    print("== local reviewer skip =="); test_local_reviewer_skips()
    print("== failed build not passed =="); test_failed_build_never_passes()
    print("== failed build retries =="); test_failed_build_retries_then_passes()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
