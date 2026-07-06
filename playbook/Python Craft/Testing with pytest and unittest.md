# Testing with pytest and unittest

Anvil's build gate reads your test's exit code — so write tests that actually assert
behavior, and make sure they RUN (a test file with no discovered tests is a red flag).

## pytest — least boilerplate (`python -m pip install pytest`)
```python
# test_core.py  — functions named test_*, plain assert
from mymodule import add, ai_move
import chess

def test_add():
    assert add(2, 3) == 5

def test_ai_returns_legal_move():
    b = chess.Board()
    assert ai_move(b) in b.legal_moves        # test the PROPERTY, not a hardcoded move
```
Run: `python -m pytest -q`. Exit 0 = all passed.

## unittest — stdlib, no install
```python
import unittest
class TestCore(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
if __name__ == "__main__":
    unittest.main()
```
Run: `python -m unittest test_core` (or `python test_core.py`). NOTE: `unittest discover`
only finds methods on a `TestCase` subclass named `test_*` — a plain `def test_x()`
function will show "Ran 0 tests". If you write plain functions, run them yourself in
`if __name__ == "__main__":` or use pytest.

## What makes a test worth having
- Assert the PROPERTY that must hold (every AI move is legal; the maze is solvable; the
  saved file reloads equal) — not a brittle hardcoded expected value that a valid change breaks.
- Cover edge cases: empty input, one item, max size, invalid input.
- A test that imports the module and asserts nothing is not a test.

## For headless GUI/game tests
Don't launch the window — test the logic functions, or use a `--selftest` that steps a few
frames offscreen. See [[Headless self-test for games]] and [[Writing a build that passes review]].
