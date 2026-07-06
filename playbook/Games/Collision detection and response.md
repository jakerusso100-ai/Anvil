# Collision detection and response

The physics of most 2D games: detect overlaps, then push objects apart. Get this right and
"can't walk through walls", "stand on platforms", and "pick up items" all work.

## AABB (axis-aligned boxes) — the workhorse
```python
def aabb(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx+bw and ax+aw > bx and ay < by+bh and ay+ah > by
```
pygame has this built in: `rect_a.colliderect(rect_b)` and `rect.collidelist(rects)`.

## Circle collision (distance test)
```python
def circles_hit(x1,y1,r1, x2,y2,r2):
    dx, dy = x2-x1, y2-y1
    return dx*dx + dy*dy <= (r1+r2)**2      # compare squared distances (no sqrt)
```

## Wall collision the RIGHT way — resolve X and Y separately
Move on one axis, check, undo if it hit; then the other axis. This lets you slide along
walls instead of sticking.
```python
def move_with_collision(rect, dx, dy, walls):
    rect.x += dx
    for w in walls:
        if rect.colliderect(w):
            rect.x -= dx; break
    rect.y += dy
    for w in walls:
        if rect.colliderect(w):
            rect.y -= dy; break
```

## Gravity / platforms
Track vertical velocity: `vy += GRAVITY*dt`; move by `vy`; if you land on a platform
(collide while moving down), set `vy = 0` and snap to the platform top (`rect.bottom = plat.top`).

## Testing collision in a headless self-test
Assert the property: put the player next to a wall, push toward it, assert it did NOT pass
through (`assert not player.colliderect(wall)` after the move). See [[Headless self-test for games]].
For real 3D physics (gravity + capsule collision) use Bullet — see [[Panda3D first-person walking sim]].
