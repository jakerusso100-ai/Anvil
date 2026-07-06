# pygame game template (with headless self-test)

A clean, complete structure for any 2D pygame game (or a raycasting pseudo-3D one).
Needs `python -m pip install pygame` (pygame-ce on Python 3.13+). Fill in `update()` and
`draw()`; the loop, timing, and self-test are already correct.

```python
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # headless-safe (selftest)
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

W, H, FPS = 800, 600, 60

def update(state, dt, keys):
    ...   # move the player/entities; handle collision here

def draw(screen, state):
    screen.fill((20, 20, 30))
    ...   # blit sprites / draw shapes
    pygame.display.flip()

def new_state():
    return {"player": [W//2, H//2], "npcs": [[100,100],[400,300]]}

def run(headless=False, frames=None):
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    state = new_state()
    running, n = True, 0
    while running:
        dt = clock.tick(FPS) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
        keys = pygame.key.get_pressed()
        update(state, dt, keys)
        draw(screen, state)
        n += 1
        if frames is not None and n >= frames: running = False   # selftest exits
    pygame.quit()
    return state

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        s = run(headless=True, frames=120)
        assert s is not None, "game did not initialise"
        print("[selftest] ran 120 frames headlessly, OK")
        sys.exit(0)
    run()
```

## Notes
- One clock, one `dt` per frame; multiply movement by `dt` so speed is frame-rate independent.
- Collision: check the player's next rect against walls BEFORE committing the move.
- See [[Headless self-test for games]] for why the `--selftest` path matters.
