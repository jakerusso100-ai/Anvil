"""Round 14 — GUI dogfood: construct the real Main window offscreen and verify every
feature added this session (Prompt mode, quality squad, checker picker, agent review,
auto-escalation) is correctly wired from settings/mode all the way to the Worker kwargs.
Catches wiring bugs the backend/unit tests can't. Run: py -3.14 -X utf8 tests/test_round14.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

import llm  # noqa: E402
import copilot  # noqa: E402
from test_anvil import FAIL, check, expect  # noqa: E402

app = QApplication.instance() or QApplication([])
llm.unload_ollama = lambda m: None
copilot.route = lambda *a, **k: {"model": "mock-model", "category": "build_app",
                                 "why": "mocked", "router_ok": True, "fit_note": None}

import main  # noqa: E402


def _capture_worker():
    """Swap Worker for a subclass that records (mode, kwargs) and never actually runs."""
    recorded = {}
    real = main.Worker

    class Rec(real):
        def __init__(self, mode, kwargs, *a, **k):
            recorded["mode"] = mode
            recorded["kwargs"] = dict(kwargs)
            super().__init__(mode, kwargs, *a, **k)

        def start(self):  # don't spawn the thread
            pass

    main.Worker = Rec
    return recorded, (lambda: setattr(main, "Worker", real))


def test_gui_constructs_with_new_controls():
    def body():
        w = main.Main()
        expect(hasattr(w, "btn_prompt"), "Prompt mode button exists")
        expect(hasattr(w, "btn_agent") and hasattr(w, "btn_chat"), "Agent/Chat buttons exist")
        w.set_mode("Prompt")
        expect(w.mode == "Prompt" and w.btn_prompt.isChecked(), "Prompt mode selectable")
        w.set_mode("Agent")
        # settings dialog builds and round-trips the new keys
        dlg = main.SettingsDialog(w, w.settings)
        vals = dlg.values()
        expect({"squad", "checker", "review_agent", "reviewer", "auto_fix"} <= set(vals),
               f"settings expose the new controls: {sorted(vals)}")
    check("gui: constructs with Prompt button + squad/checker settings", body)


def test_dispatch_squad_with_escalation():
    def body():
        w = main.Main()
        w.set_mode("Agent")
        w.settings.update({"squad": True, "checker": "", "review_agent": True,
                           "allow_api": True, "reviewer": "claude-haiku-4-5"})
        rec, restore = _capture_worker()
        try:
            w.input.setPlainText("build me a game")
            w.send()
        finally:
            restore()
        expect(rec.get("mode") == "agent", "squad runs in agent mode")
        kw = rec.get("kwargs", {})
        expect("checker_model" in kw, "squad passes a checker_model")
        expect(kw.get("escalate_to") == "claude-haiku-4-5",
               "allow_api -> auto-escalation wired to the reviewer model")
    check("gui: Agent+squad+allow_api -> checker_model + escalate_to", body)


def test_dispatch_review_and_prompt_and_chat():
    def body():
        w = main.Main()
        # Agent + review (squad off) -> review kwargs, no checker
        w.set_mode("Agent")
        w.settings.update({"squad": False, "review_agent": True, "reviewer": "claude-haiku-4-5",
                           "auto_fix": True, "rounds": 2})
        rec, restore = _capture_worker()
        try:
            w.input.setPlainText("hello"); w.send()
        finally:
            restore()
        kw = rec.get("kwargs", {})
        expect("review" in kw and "checker_model" not in kw, "review path, not squad")

        # Prompt mode -> prompt worker
        w.set_mode("Prompt")
        rec2, restore2 = _capture_worker()
        try:
            w.input.setPlainText("build me something"); w.send()
        finally:
            restore2()
        expect(rec2.get("mode") == "prompt", "Prompt mode dispatches the prompt worker")

        # Chat mode -> chat worker with review settings
        w.set_mode("Chat")
        rec3, restore3 = _capture_worker()
        try:
            w.input.setPlainText("explain this"); w.send()
        finally:
            restore3()
        expect(rec3.get("mode") == "chat", "Chat mode dispatches the chat worker")
        expect("reviewer" in rec3.get("kwargs", {}), "chat carries the reviewer")
    check("gui: review / Prompt / Chat all dispatch correctly", body)


def test_vision_attach_routes_to_vlm():
    def body():
        w = main.Main()
        w.set_mode("Agent")   # an attached image overrides the mode -> vision chat
        w.attached_image_b64 = "ZmFrZS1iNjQ="   # fake base64
        w.attached_image_name = "shot.png"
        rec, restore = _capture_worker()
        try:
            w.input.setPlainText("what's in this screenshot?")
            w.send()
        finally:
            restore()
        expect(rec.get("mode") == "chat", "vision turn dispatches a chat worker")
        kw = rec.get("kwargs", {})
        expect(kw.get("model") == copilot.ROSTER["vision"], "routes to the vision model")
        expect(kw.get("messages", [{}])[-1].get("images") == ["ZmFrZS1iNjQ="],
               "the image is attached to the last user message")
        expect(kw.get("review") is False, "no code-review pass on a vision turn")
        expect(w.attached_image_b64 is None, "attachment cleared after send")
    check("gui: attaching an image routes the turn to the vision model", body)


if __name__ == "__main__":
    print("== construct + controls =="); test_gui_constructs_with_new_controls()
    print("== vision attach =="); test_vision_attach_routes_to_vlm()
    print("== squad + escalation dispatch =="); test_dispatch_squad_with_escalation()
    print("== review/prompt/chat dispatch =="); test_dispatch_review_and_prompt_and_chat()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
