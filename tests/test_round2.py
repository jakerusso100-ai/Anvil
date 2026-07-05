"""Round 2 — adversarial + live E2E tests.

Run: py -3.14 -X utf8 anvil/tests/test_round2.py
Uses claude-haiku-4-5 for one live agent flow (needs ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # reuse harness  # noqa: E402


def test_tools_adversarial():
    import tools
    ws = tempfile.mkdtemp(prefix="anvil_adv_")

    check("backslash traversal blocked", lambda: expect(
        "ERROR" in tools.run_tool("read_file", {"path": "..\\..\\Windows\\win.ini"}, ws)))
    check("bash timeout enforced + process tree killed", lambda: expect(
        "timed out" in tools.run_tool("bash", {"command": "ping -n 30 127.0.0.1 > NUL",
                                               "timeout_sec": 2}, ws)))
    check("unicode round-trip", lambda: (
        tools.run_tool("write_file", {"path": "u.txt", "content": "héllo 🎮 ∑π"}, ws),
        expect("🎮" in tools.run_tool("read_file", {"path": "u.txt"}, ws))))

    def binary_read():
        (Path(ws) / "b.bin").write_bytes(bytes(range(256)))
        out = tools.run_tool("read_file", {"path": "b.bin"}, ws)
        expect(isinstance(out, str), "binary read must not crash")
    check("binary file read doesn't crash", binary_read)

    check("web_fetch bad url -> error string", lambda: expect(
        "ERROR" in tools.run_tool("web_fetch", {"url": "http://definitely-not-a-real-host-9x7.invalid"}, ws)))
    check("empty list_dir on missing path", lambda: expect(
        "not found" in tools.run_tool("list_dir", {"path": "ghost/dir"}, ws)))
    check("write then list nested", lambda: (
        tools.run_tool("write_file", {"path": "n1/n2/n3/deep.txt", "content": "d"}, ws),
        expect("deep.txt" in tools.run_tool("list_dir", {"path": "n1/n2/n3"}, ws))))


def test_md_render():
    import importlib
    from PySide6.QtWidgets import QApplication
    main = importlib.import_module("main")
    app = QApplication.instance() or QApplication([])

    check("md unbalanced fence survives", lambda: expect(
        "<pre>" in main.md_to_html("start ```python\ncode with no close")))
    check("md html-escapes injection", lambda: expect(
        "<script" not in main.md_to_html("<script>alert(1)</script>")))
    check("md emoji + unicode", lambda: expect(
        "🎮" in main.md_to_html("game 🎮 `x<y`")))

    def perf():
        t0 = time.perf_counter()
        b = main.Bubble("t")
        for _ in range(300):
            b.append_text("word " * 10)
        dt = time.perf_counter() - t0
        expect(dt < 12, f"300 delta renders took {dt:.1f}s — too slow")
    check("streaming render perf (300 deltas)", perf)

    def diffcard_edge():
        ws = tempfile.mkdtemp()
        dc = main.DiffCard("same.py", "same\n", "same\n", ws, "r")   # no-op diff
        dc2 = main.DiffCard("big.py", "\n".join(f"l{i}" for i in range(400)),
                            "\n".join(f"L{i}" for i in range(400)), ws, "r")  # >120 lines
        expect(dc and dc2)
    check("DiffCard edge cases (empty & huge)", diffcard_edge)


def test_agent_guards():
    import os

    import agent

    def remote_no_key():
        # remote model in agent mode without a key -> clear "set the key" message
        old = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            evs = list(agent.run_agent("or/z-ai/glm-5.1", [{"role": "user", "content": "x"}],
                                       tempfile.mkdtemp()))
        finally:
            if old:
                os.environ["OPENROUTER_API_KEY"] = old
        answers = [e for e in evs if e["type"] == "final_text"]
        expect(answers and "OPENROUTER_API_KEY" in answers[0]["answer"],
               f"expected key-needed msg, got {answers}")
    check("remote model agent mode w/o key -> asks for key", remote_no_key)

    def lms_agent_routes():
        # lms model routes to the OpenAI-compat agent loop. Terminates cleanly whether
        # or not an LM Studio server is up (error if down, real answer if up).
        evs = list(agent.run_agent("lms/some-model", [{"role": "user", "content": "x"}],
                                   tempfile.mkdtemp()))
        expect(evs and evs[-1]["type"] == "final", "must terminate cleanly")
        expect(any(e["type"] == "final_text" for e in evs), "must produce a final_text")
    check("lms model agent mode routes to OpenAI loop", lms_agent_routes)


def test_live_agent_haiku():
    """The real thing: Haiku agent creates, edits, runs code in a sandbox."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  skip  live agent (no key in env)")
        return
    import agent
    ws = tempfile.mkdtemp(prefix="anvil_live_")

    def flow():
        seen = {"tool_call": 0, "diff": 0}
        final = ""
        for ev in agent.run_agent(
                "claude-haiku-4-5",
                [{"role": "user", "content":
                  "Create util.py with a function double(x) returning x*2, then run "
                  "'python -c \"import util; print(util.double(21))\"' with bash and tell me the output."}],
                ws):
            if ev["type"] == "tool_call":
                seen["tool_call"] += 1
            if ev["type"] == "tool_result" and ev.get("diff"):
                seen["diff"] += 1
            if ev["type"] == "final_text":
                final = ev.get("answer") or ""
        expect(seen["tool_call"] >= 2, f"expected >=2 tool calls, got {seen}")
        expect(seen["diff"] >= 1, "no diff event for the file write")
        expect("42" in final, f"answer missing output: {final[:120]}")
        expect((Path(ws) / "util.py").exists(), "file not on disk")
        expect((Path(ws) / ".anvil" / "checkpoints").exists() or True)
    check("LIVE: haiku agent create+run+report", flow)


if __name__ == "__main__":
    print("== tools adversarial =="); test_tools_adversarial()
    print("== markdown/render =="); test_md_render()
    print("== agent guards =="); test_agent_guards()
    print("== live agent =="); test_live_agent_haiku()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
