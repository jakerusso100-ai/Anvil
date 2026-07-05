"""Round 3 — thread lifecycle, state leaks, multi-turn stress.

Run: py -3.14 -X utf8 anvil/tests/test_round3.py
No network needed: pipeline/agent generators are monkeypatched.
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

from test_anvil import FAIL, check, expect  # noqa: E402

import importlib  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

main = importlib.import_module("main")
import copilot  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402

app = QApplication.instance() or QApplication([])

# Unit tests must NEVER touch live Ollama: mock the router and the unloader.
llm.unload_ollama_real = llm.unload_ollama
llm.unload_ollama = lambda m: None
copilot.route = lambda *a, **k: {"model": "mock-model", "category": "small_code",
                                 "why": "mocked", "router_ok": True}


def fake_turn_events(n_tools: int = 1):
    evs = [{"type": "stage", "stage": "coding", "model": "mock"}]
    evs += [{"type": "delta", "channel": "coder", "round": 0, "text": f"chunk{i} "} for i in range(5)]
    for i in range(n_tools):
        evs.append({"type": "tool_call", "name": "bash", "args": {"command": f"echo {i}"}})
        evs.append({"type": "tool_result", "name": "bash", "output": f"[exit 0]\n{i}",
                    "denied": False, "diff": None, "run_id": "mock"})
    evs.append({"type": "final", "cost": 0.0, "reviewed": False, "revised": False,
                "passed": None, "answer": "mock answer"})
    return evs


def make_window():
    w = main.Main()
    w.workspace = tempfile.mkdtemp(prefix="anvil_r3_")
    return w


def drive_turn(w, text="do something", events=None, mode="Chat"):
    """Simulate a full turn synchronously through the real Worker (no thread)."""
    events = events if events is not None else fake_turn_events()
    real = pipeline.run_turn
    pipeline.run_turn = lambda **kw: iter(events)
    try:
        w.set_mode(mode)
        w.input.setPlainText(text)
        # send() creates the worker but we run it synchronously for determinism
        orig_start = main.Worker.start
        main.Worker.start = lambda self: self.run()
        try:
            w.send()
        finally:
            main.Worker.start = orig_start
        app.processEvents()
    finally:
        pipeline.run_turn = real


def test_turn_lifecycle():
    w = make_window()

    def one_turn():
        drive_turn(w)
        expect(w.history[-1]["content"] == "mock answer", "answer not committed")
        expect(w.send_btn.text() == "➤", "send button not restored")
    check("single mocked turn completes", one_turn)

    def three_turns():
        for _ in range(3):
            drive_turn(w)
        assistants = [m for m in w.history if m["role"] == "assistant"]
        expect(len(assistants) >= 4, f"history wrong: {len(assistants)}")
    check("three sequential turns", three_turns)

    def clear_between():
        drive_turn(w)
        w.slash("/clear")
        drive_turn(w)  # must not touch deleted widgets
        expect(w.history[-1]["content"] == "mock answer")
    check("turn -> /clear -> turn (no dead widgets)", clear_between)

    def double_send_guard():
        w.input.setPlainText("x")
        w.worker = main.Worker("chat", {"model": "m", "messages": []}, "Bypass", "r", True, "x",
                               w.workspace)
        # fake running state
        real_running = main.Worker.isRunning
        main.Worker.isRunning = lambda self: True
        try:
            before = len(w.history)
            w.send()
            expect(len(w.history) == before, "send while running must be a no-op")
        finally:
            main.Worker.isRunning = real_running
    check("double-send guard", double_send_guard)


def test_stop_flag():
    def stop_mid_stream():
        w = make_window()
        events = fake_turn_events()
        real = pipeline.run_turn

        def slow_gen(**kw):
            for i, ev in enumerate(events):
                if i == 3:
                    w.worker.stopping = True  # user pressed stop mid-stream
                yield ev
        pipeline.run_turn = slow_gen
        orig_start = main.Worker.start
        main.Worker.start = lambda self: self.run()
        try:
            w.set_mode("Chat")
            w.input.setPlainText("stop me")
            w.send()
            app.processEvents()
        finally:
            main.Worker.start = orig_start
            pipeline.run_turn = real
        expect(w.send_btn.text() == "➤", "button not restored after stop")
    check("stop mid-stream restores UI", stop_mid_stream)


def test_bubble_leak():
    def storm_x50():
        w = make_window()
        t0 = time.perf_counter()
        for _ in range(50):
            drive_turn(w, events=fake_turn_events(n_tools=2))
        dt = time.perf_counter() - t0
        # 50 turns x ~10 events; the chat column will be long but must stay responsive
        expect(dt < 30, f"50 turns took {dt:.1f}s")
        expect(len(w.history) == 100, f"history len {len(w.history)}")
    check("50-turn stress (bubble buildup)", storm_x50)


def test_unload_logic():
    import llm
    calls = []

    def fake_unload(m):
        calls.append(m)

    def flow():
        w = make_window()
        real = llm.unload_ollama
        llm.unload_ollama = fake_unload
        try:
            # AUTO -> no unload; local -> local switch -> unload once; api -> no unload
            for model in ("gpt-oss:20b", "qwen3-coder:30b", "claude-haiku-4-5"):
                i = w.coder.findData(model)
                if i >= 0:
                    w.coder.setCurrentIndex(i)
                drive_turn(w)
            # each switch away from a local model frees its VRAM:
            # gpt-oss -> qwen3-coder (unload gpt-oss), qwen3-coder -> haiku (unload qwen3-coder)
            expect(calls == ["gpt-oss:20b", "qwen3-coder:30b"], f"unload calls wrong: {calls}")
        finally:
            llm.unload_ollama = real
    check("unload-on-switch fires exactly once", flow)


def test_settings_dialog():
    def roundtrip():
        w = make_window()
        dlg = main.SettingsDialog(w, w.settings)
        vals = dlg.values()
        expect(vals["reviewer"] == w.settings["reviewer"])
        expect(set(vals) >= {"reviewer", "review", "auto_fix", "rounds", "router", "allow_api"})
    check("settings dialog round-trip", roundtrip)


def test_slash_edges():
    w = make_window()
    check("unknown slash safe", lambda: expect(w.slash("/bogus") is True))
    check("/model invalid safe", lambda: expect(w.slash("/model not-a-model") is True))
    check("/model valid switches", lambda: (
        w.slash("/model claude-haiku-4-5"),
        expect(w.coder.currentData() == "claude-haiku-4-5")))


if __name__ == "__main__":
    print("== turn lifecycle =="); test_turn_lifecycle()
    print("== stop flag =="); test_stop_flag()
    print("== 50-turn stress =="); test_bubble_leak()
    print("== unload logic =="); test_unload_logic()
    print("== settings =="); test_settings_dialog()
    print("== slash edges =="); test_slash_edges()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
