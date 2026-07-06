# Error handling and robustness

Programs that pass review handle the unhappy path: missing files, bad input, network
failures, empty collections. Rules that prevent the common crashes.

## Catch specific exceptions, not bare `except`
```python
try:
    data = json.loads(path.read_text())
except FileNotFoundError:
    data = default()
except json.JSONDecodeError:
    log("corrupt save, starting fresh"); data = default()
```
- Bare `except:` hides bugs (and swallows Ctrl-C). Catch what you expect and can handle.
- Don't catch just to `pass` silently — log it or recover meaningfully.

## Validate input at the boundary
```python
n = input("how many? ")
if not n.isdigit():
    print("please enter a number"); return
n = int(n)
```
Guard against division by zero, out-of-range indices, empty lists (`if not items: ...`).

## Fail loud in dev, degrade gracefully in prod
- Use `assert` for "this should never happen" invariants (they document + catch bugs).
- For expected failures (network down, file missing), recover and tell the user.

## Timeouts and resources
- Any network call gets a `timeout=`. Any subprocess gets a timeout.
- Use context managers (`with open(...) as f:`, `with sqlite3.connect(...) as con:`) so
  files/handles close even on error.

## The classic Python foot-guns
- Mutable default args: `def f(x=[])` shares the list — use `def f(x=None): x = x or []`.
- Modifying a list while iterating it — iterate a copy (`for i in list(items):`).
- `is` vs `==` — use `==` for value equality, `is` only for `None`/singletons.
- Integer/float division, off-by-one in ranges. Test edge cases (0, 1, empty, negative).
