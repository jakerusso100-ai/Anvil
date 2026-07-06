# Raycasting pseudo-3D engine (Wolfenstein-style first person)

The cheapest way to get a "3D" first-person game in pure pygame — no 3D engine, no
Panda3D. You cast one ray per screen column across the player's field of view, find the
wall distance, and draw a vertical strip whose height is inversely proportional to
distance. Great for maze games, corridor shooters, and walking sims.

## Core idea
- World = a 2D grid `MAP[y][x]` where non-zero = wall.
- Player has `(x, y)` position and `angle` (radians). FOV ~ 60° (`math.pi/3`).
- For each screen column, cast a ray from the player at `angle - FOV/2 + col/W*FOV`,
  step until it hits a wall, record distance, draw a wall slice.
- Fix "fisheye" by multiplying distance by `cos(ray_angle - player_angle)`.

## Minimal DDA-ish caster
```python
import math, pygame, os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
W, H, FOV = 640, 480, math.pi/3
MAP = ["########","#......#","#..##..#","#......#","#..NPC.#","########"]
def cast(px, py, ang):
    sin, cos = math.sin(ang), math.cos(ang)
    for depth in range(1, 2000):
        d = depth * 0.02
        x, y = px + cos*d, py + sin*d
        if MAP[int(y)][int(x)] == '#':
            return d
    return 20.0
def render(screen, px, py, pa):
    screen.fill((0,0,0))
    for col in range(W):
        ang = pa - FOV/2 + (col/W)*FOV
        dist = cast(px, py, ang) * math.cos(ang - pa)   # de-fisheye
        h = min(H, int(H / (dist + 0.0001)))
        shade = max(0, 255 - int(dist*20))
        pygame.draw.line(screen, (shade,shade,shade), (col,(H-h)//2), (col,(H+h)//2))
    pygame.display.flip()
```
Player moves with WASD (advance along `angle`, block if the target cell is a wall —
that's your collision/physics). Turn with A/D or mouse. NPCs = billboarded sprites drawn
by distance (draw farther ones first). Add a `--selftest` that renders a few frames
headless (see [[Headless self-test for games]]).

## Why choose this over Panda3D
- Pure pygame, no heavy deps, easy to headless-test.
- Good enough to look 3D. If you need real 3D physics/gravity, use [[Panda3D first-person walking sim]] instead.
