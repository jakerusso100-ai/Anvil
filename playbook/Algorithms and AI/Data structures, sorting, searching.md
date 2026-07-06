# Data structures, sorting, searching (pick the right one)

Choosing the right structure often turns a slow/buggy solution into a simple fast one.

## Python built-ins and when to reach for them
- **list** — ordered, indexable. Append/pop-end O(1); insert/remove-middle and `x in list` O(n).
- **dict** — key→value, O(1) lookup/insert. Use for counting, caching, adjacency, "seen".
- **set** — membership + dedup, O(1) `in`. Use to remove duplicates and test presence fast.
- **collections.deque** — O(1) push/pop at BOTH ends. Use for queues/BFS (a list is O(n) at the front).
- **collections.Counter** — counts things: `Counter(words).most_common(3)`.
- **collections.defaultdict** — auto-default: `d = defaultdict(list); d[k].append(v)`.
- **heapq** — priority queue (min-heap): `heappush/heappop`. Use for Dijkstra/A*/"top-k".

## Sorting (don't hand-roll — `sorted` is fast and correct)
```python
sorted(items)                                  # ascending
sorted(items, key=lambda x: x.score, reverse=True)   # by field, descending
items.sort(key=lambda p: (p.last, p.first))    # in-place, multi-key
```
Only write your own sort to demonstrate an algorithm; otherwise use `sorted`/`.sort`.

## Searching
- Unsorted → linear scan or put items in a `set`/`dict` for O(1) lookups.
- Sorted list → binary search with `bisect`:
```python
import bisect
i = bisect.bisect_left(sorted_list, target)
found = i < len(sorted_list) and sorted_list[i] == target
```

## Graph traversal (BFS/DFS)
```python
from collections import deque
def bfs(graph, start):
    seen, q = {start}, deque([start])
    while q:
        node = q.popleft()
        for nb in graph[node]:
            if nb not in seen:
                seen.add(nb); q.append(nb)
    return seen
```
BFS (deque) = shortest path in unweighted graphs; weighted → heapq/Dijkstra; grid with
obstacles → [[A-star pathfinding for NPCs]].
