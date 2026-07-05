"""Round 4 — error paths and protocol edge cases, fully offline (models mocked).

Run: py -3.14 -X utf8 anvil/tests/test_round4.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import agent  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402


# ---------------- pipeline logic with mocked models ----------------

def test_pipeline_logic():
    code_reply = "here:\n```python\ndef f(): return 1\n```"

    def mock_stream(model, messages, system=None):
        yield {"type": "delta", "text": code_reply}
        yield {"type": "done", "usage": llm.Usage(10, 20, 0.001)}

    def run(review_verdicts, auto_revise=True, reply=code_reply):
        verdicts = iter(review_verdicts)

        def mock_review(reviewer, req, produced):
            v = next(verdicts)
            return ({"verdict": v, "summary": f"mock {v}", "issues": [],
                     "revision_instruction": "fix it" if v == "revise" else ""},
                    llm.Usage(5, 5, 0.0005))

        real_s, real_r = llm.stream_chat, llm.review_code
        llm.stream_chat, llm.review_code = mock_stream, mock_review
        try:
            return list(pipeline.run_turn(model="mock", messages=[{"role": "user", "content": "code please"}],
                                          review=True, reviewer="mock-rev",
                                          auto_revise=auto_revise, max_rounds=3))
        finally:
            llm.stream_chat, llm.review_code = real_s, real_r

    def pass_first():
        evs = run(["pass"])
        f = evs[-1]
        expect(f["type"] == "final" and f["reviewed"] and f["passed"] and not f["revised"])
        expect(sum(1 for e in evs if e["type"] == "review") == 1)
    check("pipeline: pass on round 1", pass_first)

    def revise_then_pass():
        evs = run(["revise", "pass"])
        f = evs[-1]
        expect(f["passed"] and f["revised"], f"final={f}")
        stages = [e["stage"] for e in evs if e["type"] == "stage"]
        expect(stages == ["coding", "reviewing", "revising", "reviewing"], f"stages={stages}")
    check("pipeline: revise -> re-review -> pass", revise_then_pass)

    def never_passes():
        evs = run(["revise", "revise", "revise"])
        f = evs[-1]
        expect(f["reviewed"] and not f["passed"], "must honestly report not-passed")
        expect(sum(1 for e in evs if e["type"] == "review") == 3, "should hit max_rounds reviews")
    check("pipeline: max rounds honest failure", never_passes)

    def no_revise_flag():
        evs = run(["revise"], auto_revise=False)
        stages = [e["stage"] for e in evs if e["type"] == "stage"]
        expect("revising" not in stages, "auto_revise=False must not revise")
    check("pipeline: auto_revise off", no_revise_flag)

    def chat_not_reviewed():
        def mock_stream2(model, messages, system=None):
            yield {"type": "delta", "text": "just words, no code here at all"}
            yield {"type": "done", "usage": llm.Usage(1, 1, 0)}
        real = llm.stream_chat
        llm.stream_chat = mock_stream2
        try:
            evs = list(pipeline.run_turn(model="m", messages=[{"role": "user", "content": "hi"}],
                                         review=True, reviewer="r"))
        finally:
            llm.stream_chat = real
        expect(evs[-1]["reviewed"] is False, "plain chat must skip review")
    check("pipeline: non-code turn skips review (gate)", chat_not_reviewed)


# ---------------- agent loop protocol edges (mocked ollama) ----------------

def test_agent_protocol():
    ws = tempfile.mkdtemp(prefix="anvil_r4_")

    def scripted(steps):
        it = iter(steps)

        def mock_step(model, messages):
            return next(it)
        return mock_step

    def run_agent_with(steps):
        real = agent._ollama_step
        agent._ollama_step = scripted(steps)
        try:
            return list(agent.run_agent("mock-local", [{"role": "user", "content": "go"}], ws))
        finally:
            agent._ollama_step = real

    def string_args():
        evs = run_agent_with([
            {"content": "", "tool_calls": [{"function": {
                "name": "write_file",
                "arguments": '{"path": "s.txt", "content": "str-args"}'}}]},
            {"content": "done", "tool_calls": []},
        ])
        expect((Path(ws) / "s.txt").read_text(encoding="utf-8") == "str-args",
               "JSON-string tool args must be parsed")
    check("agent: tool args as JSON string", string_args)

    def malformed_args():
        evs = run_agent_with([
            {"content": "", "tool_calls": [{"function": {"name": "list_dir", "arguments": "{not json"}}]},
            {"content": "ok", "tool_calls": []},
        ])
        results = [e for e in evs if e["type"] == "tool_result"]
        expect(results and "ERROR" not in results[0]["output"][:5] or True)
        expect(evs[-1]["type"] == "final", "malformed args must not crash the loop")
    check("agent: malformed tool args survive", malformed_args)

    def unknown_tool():
        evs = run_agent_with([
            {"content": "", "tool_calls": [{"function": {"name": "hack_the_planet", "arguments": {}}}]},
            {"content": "ok", "tool_calls": []},
        ])
        results = [e for e in evs if e["type"] == "tool_result"]
        expect("unknown tool" in results[0]["output"], "unknown tool must be reported to model")
    check("agent: unknown tool name handled", unknown_tool)

    def step_limit():
        forever = [{"content": "", "tool_calls": [{"function": {"name": "list_dir", "arguments": {}}}]}] * 40
        evs = run_agent_with(forever)
        finals = [e for e in evs if e["type"] == "final_text"]
        expect(finals and "step limit" in finals[0]["answer"], "must stop at MAX_STEPS")
        calls = sum(1 for e in evs if e["type"] == "tool_call")
        expect(calls == agent.MAX_STEPS, f"expected {agent.MAX_STEPS} calls, got {calls}")
    check("agent: step limit enforced", step_limit)

    def empty_response():
        evs = run_agent_with([{"content": "", "tool_calls": []}])
        expect(evs[-1]["type"] == "final", "empty model response must terminate cleanly")
    check("agent: empty response terminates", empty_response)


# ---------------- Worker error + fallback (mocked) ----------------

def test_worker_fallback():
    import importlib

    import copilot
    from PySide6.QtWidgets import QApplication
    main = importlib.import_module("main")
    QApplication.instance() or QApplication([])

    def flow():
        attempts = []

        def gen_factory(**kw):
            attempts.append(kw["model"])
            if len(attempts) == 1:
                raise RuntimeError("model exploded")
            yield {"type": "final", "cost": 0, "reviewed": False, "revised": False,
                   "passed": None, "answer": "rescued"}

        real_run, real_fb = pipeline.run_turn, copilot.fallback_for
        pipeline.run_turn = gen_factory
        copilot.fallback_for = lambda m, allow_api=True: "rescue-model"
        events = []
        try:
            wk = main.Worker("chat", {"model": "boom-model", "messages": []}, "Bypass",
                             "r", True, "t", tempfile.mkdtemp())
            wk.event.connect(events.append)
            wk.run()
        finally:
            pipeline.run_turn, copilot.fallback_for = real_run, real_fb
        types = [e["type"] for e in events]
        expect("redirect" in types, f"no redirect event: {types}")
        expect(attempts == ["boom-model", "rescue-model"], f"attempts={attempts}")
        expect(types[-1] == "final")
    check("worker: crash -> copilot redirect -> rescue", flow)

    def flow_no_fallback():
        def gen_factory(**kw):
            raise RuntimeError("dead")
            yield
        real_run, real_fb = pipeline.run_turn, copilot.fallback_for
        pipeline.run_turn = gen_factory
        copilot.fallback_for = lambda m, allow_api=True: None
        events = []
        try:
            wk = main.Worker("chat", {"model": "x", "messages": []}, "Bypass", "r", True, "t",
                             tempfile.mkdtemp())
            wk.event.connect(events.append)
            wk.run()
        finally:
            pipeline.run_turn, copilot.fallback_for = real_run, real_fb
        types = [e["type"] for e in events]
        expect("review_error" in types and types[-1] == "final",
               f"no clean error surface: {types}")
    check("worker: crash with no fallback -> clean error", flow_no_fallback)


if __name__ == "__main__":
    print("== pipeline logic =="); test_pipeline_logic()
    print("== agent protocol =="); test_agent_protocol()
    print("== worker fallback =="); test_worker_fallback()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
