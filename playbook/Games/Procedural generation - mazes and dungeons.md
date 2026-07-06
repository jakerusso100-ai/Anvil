# Procedural generation — mazes, dungeons, terrain

Generate levels instead of hand-authoring them. Two reliable algorithms + a noise trick.

## Maze — recursive backtracker (perfect maze, always solvable)
```python
import random
def make_maze(w, h):
    # cells on odd coords; grid of 1=wall, 0=floor. w,h odd.
    grid = [[1]*w for _ in range(h)]
    def carve(x, y):
        grid[y][x] = 0
        for dx, dy in random.sample([(2,0),(-2,0),(0,2),(0,-2)], 4):
            nx, ny = x+dx, y+dy
            if 0 < nx < w-1 and 0 < ny < h-1 and grid[ny][nx] == 1:
                grid[y+dy//2][x+dx//2] = 0   # knock down the wall between
                carve(nx, ny)
    carve(1, 1)
    return grid
```

## Dungeon — random rooms + corridors
```python
import random
def make_dungeon(w, h, rooms=8):
    grid = [[1]*w for _ in range(h)]; centers = []
    for _ in range(rooms):
        rw, rh = random.randint(4,8), random.randint(4,8)
        rx, ry = random.randint(1,w-rw-1), random.randint(1,h-rh-1)
        for y in range(ry, ry+rh):
            for x in range(rx, rx+rw): grid[y][x] = 0
        centers.append((rx+rw//2, ry+rh//2))
    for (x1,y1),(x2,y2) in zip(centers, centers[1:]):   # L-shaped corridors
        for x in range(min(x1,x2), max(x1,x2)+1): grid[y1][x] = 0
        for y in range(min(y1,y2), max(y1,y2)+1): grid[y][x2] = 0
    return grid, centers
```

## Terrain / heightmaps
Use value or Perlin/simplex noise (`pip install noise` → `pnoise2`) sampled over a grid for
smooth hills. For quick fake terrain, sum a few sine waves of different frequencies.

## Verify
Assert the maze is connected (flood-fill from the start reaches the exit) — use
[[A-star pathfinding for NPCs]] and assert a path exists. A generator that can produce
unsolvable levels is a bug.
