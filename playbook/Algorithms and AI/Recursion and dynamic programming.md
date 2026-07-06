# Recursion and dynamic programming patterns

When a problem breaks into overlapping subproblems, cache the subresults (DP) instead of
recomputing them. Two mechanical ways to turn a slow recursion into a fast solution.

## 1. Memoize a recursion (top-down) — often a one-line change
```python
from functools import lru_cache
@lru_cache(maxsize=None)
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)
```
`@lru_cache` caches by arguments — arguments must be hashable (tuples not lists).

## 2. Build a table (bottom-up) — no recursion depth limit
```python
def coin_change(coins, amount):          # fewest coins to make `amount`, or -1
    INF = amount + 1
    dp = [0] + [INF]*amount
    for a in range(1, amount+1):
        for c in coins:
            if c <= a: dp[a] = min(dp[a], dp[a-c] + 1)
    return dp[amount] if dp[amount] != INF else -1
```

## The recipe
1. Define the state (what parameters identify a subproblem).
2. Write the recurrence (answer in terms of smaller states) + base case.
3. Memoize (top-down) OR fill a table in dependency order (bottom-up).

## Classic problems this solves
Fibonacci, coin change, knapsack, longest common subsequence, edit distance, grid paths,
word break, longest increasing subsequence.

## Recursion hygiene
- Always have a base case that halts. Python's recursion limit is ~1000 — for deep
  recursion use the bottom-up table or `sys.setrecursionlimit` cautiously.
- Test with a brute-force version on small inputs and assert they match.
