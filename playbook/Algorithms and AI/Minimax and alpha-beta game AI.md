# Minimax and alpha-beta — game AI for turn-based games

The standard opponent AI for chess, checkers, tic-tac-toe, Connect Four, Othello, etc.
Minimax assumes both players play optimally; alpha-beta pruning skips branches that can't
affect the result (same answer, much faster). Generic template you specialize per game:

```python
def minimax(state, depth, alpha, beta, maximizing):
    if depth == 0 or state.is_terminal():
        return state.evaluate(), None            # heuristic score, no move
    best_move = None
    if maximizing:
        value = float("-inf")
        for move in state.legal_moves():
            child = state.apply(move)
            score, _ = minimax(child, depth-1, alpha, beta, False)
            if score > value: value, best_move = score, move
            alpha = max(alpha, value)
            if alpha >= beta: break              # beta cutoff (prune)
        return value, best_move
    else:
        value = float("inf")
        for move in state.legal_moves():
            child = state.apply(move)
            score, _ = minimax(child, depth-1, alpha, beta, True)
            if score < value: value, best_move = score, move
            beta = min(beta, value)
            if beta <= alpha: break              # alpha cutoff (prune)
        return value, best_move

def best_move(state, depth=4):
    _, m = minimax(state, depth, float("-inf"), float("inf"), state.maximizing_player)
    return m
```

## To use it, your game needs
- `legal_moves()`, `apply(move)` → new state, `is_terminal()`, `evaluate()` (score from the
  maximizing player's view; +big = winning).
- **Move ordering** (try likely-good moves first) makes alpha-beta prune much more.
- **Quiescence**: at depth 0, keep searching "noisy" moves (captures) to avoid the horizon
  effect — this is what separates a strong engine from a weak one.
- Iterative deepening (search depth 1,2,3… until time runs out) gives a good move any time.

## Specific games
- Chess: don't reinvent rules — see [[Chess in Python - use python-chess]].
- Tic-tac-toe / Connect Four: small enough to search to the end (perfect play).

## Test
Assert `best_move` returns a legal move and, on a forced-win position, picks the winning move.
