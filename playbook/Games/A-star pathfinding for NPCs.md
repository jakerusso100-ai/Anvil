# A* pathfinding for NPCs and enemies

Make NPCs/enemies navigate a grid toward a target intelligently (around walls). A* is the
standard: it finds the shortest path fast using a priority queue and a heuristic.

```python
import heapq
def astar(grid, start, goal):
    # grid[y][x]: 0 = walkable, 1 = wall. start/goal = (x, y).
    def h(a, b): return abs(a[0]-b[0]) + abs(a[1]-b[1])   # Manhattan
    W, H = len(grid[0]), len(grid)
    open_pq = [(0, start)]
    came_from, g = {}, {start: 0}
    while open_pq:
        _, cur = heapq.heappop(open_pq)
        if cur == goal:
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]; path.append(cur)
            return path[::-1]
        x, y = cur
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= nx < W and 0 <= ny < H and grid[ny][nx] == 0:
                ng = g[cur] + 1
                if (nx,ny) not in g or ng < g[(nx,ny)]:
                    g[(nx,ny)] = ng
                    came_from[(nx,ny)] = cur
                    heapq.heappush(open_pq, (ng + h((nx,ny), goal), (nx,ny)))
    return None   # no path
```

## Using it for NPC behavior
- Compute a path from the NPC to its target, then step one grid cell per tick toward
  `path[1]`. Recompute when the target moves or the path is blocked.
- For a "wander" NPC, pick a random reachable cell as the goal; on arrival, pick a new one.
- Cheaper alternative for simple wandering: random walk with [[Collision detection and response]]
  (pick a direction, move if not blocked, else turn). Use A* only when NPCs must *chase*.

## Test it
Assert `astar(grid, start, goal)` returns a path whose consecutive cells are adjacent and
all walkable, and returns `None` when the goal is walled off.
