# Chess in Python - use python-chess, never hand-roll the rules

Chess rules are a trap: castling, en passant, promotion, check/checkmate, pins, and
stalemate are easy to get subtly wrong (a hand-rolled engine WILL have illegal-move bugs).
**Use the `chess` library** (`python -m pip install chess`) — it handles all rules correctly.
Then you only write the AI and the UI.

## The library gives you everything hard for free
```python
import chess
board = chess.Board()
board.legal_moves                 # all legal moves (handles castling/en passant/pins)
board.push(chess.Move.from_uci("e2e4"))
board.is_checkmate(); board.is_stalemate(); board.is_check()
board.can_claim_draw()
move in board.legal_moves         # validate a move — ALWAYS check before pushing
```

## A correct minimax AI on top
```python
import chess
VALUES = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3, chess.ROOK:5, chess.QUEEN:9, chess.KING:0}

def evaluate(board):
    s = 0
    for pt, v in VALUES.items():
        s += v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return s

def minimax(board, depth, alpha, beta, maximizing):
    if depth == 0 or board.is_game_over():
        return evaluate(board), None
    best = None
    if maximizing:
        v = -1e9
        for m in board.legal_moves:
            board.push(m); sc,_ = minimax(board, depth-1, alpha, beta, False); board.pop()
            if sc > v: v, best = sc, m
            alpha = max(alpha, v)
            if beta <= alpha: break
        return v, best
    else:
        v = 1e9
        for m in board.legal_moves:
            board.push(m); sc,_ = minimax(board, depth-1, alpha, beta, True); board.pop()
            if sc < v: v, best = sc, m
            beta = min(beta, v)
            if beta <= alpha: break
        return v, best

def ai_move(board, depth=3):
    _, move = minimax(board, depth, -1e9, 1e9, board.turn == chess.WHITE)
    return move
```

## Self-test that actually proves legality
```python
def run_selftest():
    b = chess.Board()
    for _ in range(10):
        m = ai_move(b, 2)
        assert m in b.legal_moves, f"AI produced an illegal move: {m}"
        b.push(m)
        if b.is_game_over(): break
    print("[selftest] AI made only legal moves — OK")
```
Do NOT write a test that hard-codes a move sequence and asserts a specific move is legal —
that's how you get false failures. Test the *property* (every AI move is in `legal_moves`).
