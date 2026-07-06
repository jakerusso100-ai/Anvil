# Project structure, dataclasses, and type hints

## Layout for anything bigger than one file
```
myproject/
  main.py            # entry point (thin — parses args, calls into modules)
  game/              # a package (has __init__.py)
    __init__.py
    world.py
    entities.py
  tests/
    test_game.py
  requirements.txt   # pinned deps, one per line
  README.md
```
- Keep logic in importable modules; keep `main.py` thin so tests can import the logic
  without running the app. Run as `python -m myproject.main` or `python main.py`.
- One clear responsibility per module. Avoid giant single files once past ~300 lines.

## Model data with dataclasses (not loose dicts)
```python
from dataclasses import dataclass, field
@dataclass
class Player:
    x: float = 0.0
    y: float = 0.0
    hp: int = 100
    inventory: list[str] = field(default_factory=list)   # NEVER `= []` as a default
```
- `field(default_factory=list)` for mutable defaults — a bare `= []` is a classic bug
  (shared across instances).
- Dataclasses give you `__init__`, `__repr__`, and `__eq__` for free.

## Type hints help you AND the reader
```python
def move(p: Player, dx: float, dy: float) -> None: ...
def find(items: list[dict], key: str) -> dict | None: ...
```
Hints document intent and catch mistakes; they don't slow anything down. Use `X | None`
for "maybe", `list[X]`/`dict[K,V]` for containers.

## Naming
Match the surrounding code. `snake_case` functions/vars, `CapWords` classes, `UPPER` consts.
Descriptive over clever. See [[Writing a build that passes review]].
