"""Round 6 — the windowed-app guard (regression for the live-demo hang)."""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import tools  # noqa: E402


def test_gui_guard():
    ws = tempfile.mkdtemp(prefix="anvil_guard_")

    # a windowed pygame program with an infinite loop (the exact hang shape)
    (Path(ws) / "win.py").write_text(textwrap.dedent("""
        import pygame
        pygame.init(); pygame.display.set_mode((320, 240))
        while True:
            for e in pygame.event.get(): pass
            pygame.display.flip()
    """), encoding="utf-8")

    def no_hang():
        t0 = time.perf_counter()
        out = tools.run_tool("bash", {"command": "python win.py", "timeout_sec": 4}, ws)
        dt = time.perf_counter() - t0
        expect(dt < 15, f"guard hung: {dt:.1f}s")
        expect("timed out" in out and "headless" in out, f"missing note: {out[:120]}")
    check("infinite-loop GUI program times out, not hangs", no_hang)

    def tree_killed():
        # after a timeout, no orphan python window should remain from our run
        out = tools.run_tool("bash", {"command": "python win.py", "timeout_sec": 3}, ws)
        expect("[exit -1]" in out, f"expected killed exit code: {out[:80]}")
    check("process tree killed on timeout", tree_killed)

    def headless_pygame_passes():
        (Path(ws) / "ok.py").write_text(textwrap.dedent("""
            import pygame, sys
            pygame.init(); s = pygame.display.set_mode((200, 150))
            for i in range(20):
                for e in pygame.event.get(): pass
                s.fill((0, 0, 0)); pygame.display.flip()
            print("OK"); pygame.quit(); sys.exit(0)
        """), encoding="utf-8")
        out = tools.run_tool("bash", {"command": "python ok.py", "timeout_sec": 20}, ws)
        expect("OK" in out and "[exit 0]" in out, f"headless pygame failed: {out[:120]}")
    check("well-behaved headless pygame passes", headless_pygame_passes)

    def normal_unaffected():
        out = tools.run_tool("bash", {"command": 'python -c "print(2+2)"'}, ws)
        expect("4" in out and "[exit 0]" in out)
    check("normal commands unaffected", normal_unaffected)

    def env_injected():
        out = tools.run_tool("bash", {
            "command": 'python -c "import os; print(os.environ.get(\'SDL_VIDEODRIVER\'))"'}, ws)
        expect("dummy" in out, f"SDL dummy not injected: {out[:80]}")
    check("headless env vars injected", env_injected)


if __name__ == "__main__":
    print("== GUI guard =="); test_gui_guard()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
