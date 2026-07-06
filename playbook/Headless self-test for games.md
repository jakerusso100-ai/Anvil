# Headless self-test for games

A game or GUI program opens a window and runs an event loop forever. If you run it
directly to "test" it, it **blocks and hangs the agent**. Never do that. Instead, build
a `--selftest` mode that runs a few frames with **no window** and exits 0.

## The pattern (every game gets this)
```python
import sys
if "--selftest" in sys.argv:
    run_selftest(frames=120)   # step the sim, assert some state, then:
    sys.exit(0)                # exit 0 = pass, non-zero = fail
```
Anvil's reviewer trusts the self-test's exit code, so make it actually check behavior
(player moved, collision blocked it, NPC wandered) and `assert` — don't just print "ok".

## pygame — force the dummy video/audio driver BEFORE importing pygame
```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # no window
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
def run_selftest(frames=120):
    pygame.init()
    screen = pygame.display.set_mode((640, 480))
    clock = pygame.time.Clock()
    for _ in range(frames):
        for e in pygame.event.get():
            pass
        update(); draw(screen)
        pygame.display.flip(); clock.tick(60)
    pygame.quit()
```
(Anvil's shell already sets SDL_VIDEODRIVER=dummy, but set it yourself too.)

## Panda3D — offscreen window, then step the task manager
```python
from panda3d.core import loadPrcFileData
if "--selftest" in sys.argv:
    loadPrcFileData("", "window-type offscreen")   # MUST be before ShowBase()
    loadPrcFileData("", "audio-library-name null")
from direct.showbase.ShowBase import ShowBase
app = ShowBase()
def run_selftest(frames=240):
    start = player.getPos()
    for _ in range(frames):
        app.taskMgr.step()          # advance one frame (physics + tasks)
    assert player.getZ() > -1, "player fell through the floor"
    print("[selftest] ALL CHECKS PASSED")
```

## Rule of thumb
- Runs a fixed number of frames, then exits. Never an infinite loop in selftest.
- Exits 0 only if the checks pass; `raise AssertionError(...)` (exit != 0) on failure.
- Keep it fast (a few hundred frames max) so it finishes in seconds.
