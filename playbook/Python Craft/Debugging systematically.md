# Debugging systematically (don't flail)

When a self-test fails, the fastest path is a method, not random edits. This is exactly
where local models waste steps — follow the loop instead.

## The loop
1. **Read the WHOLE traceback, bottom-up.** The last line is the error type + message; the
   line above it is the file:line where it happened. That's usually the bug, not a mystery.
2. **Reproduce minimally.** Run just the failing function with the failing input, not the
   whole app. Print or assert the actual vs expected value at that point.
3. **Localize** — binary-search the code: is the value correct halfway through? Narrow until
   the one line that turns right into wrong is found.
4. **Fix the cause, not the symptom.** Don't wrap it in try/except to hide it — understand why.
5. **Re-run the self-test.** Confirm green. Add a test for the case that broke so it can't regress.

## Read common errors literally
- `ModuleNotFoundError: No module named 'x'` → install it (`python -m pip install x`) into
  the interpreter you RUN (see [[Python on Windows - python not python3]]). Not a code bug.
- `AttributeError: 'NoneType' object has no attribute 'y'` → something returned `None` you
  didn't expect; check the function that produced it.
- `IndexError` / `KeyError` → off-by-one or a missing key; guard the boundary.
- `<< was unexpected` / weird shell errors → wrong shell (Anvil uses bash; write POSIX).

## Cheap instrumentation
- `print(f"{var=}")` shows the name and value. Sprinkle at the boundary, then remove.
- `import traceback; traceback.print_exc()` inside an `except` shows the full stack.
- For a game, log positions/state each frame in `--selftest` and assert on them.

## Anti-patterns (what NOT to do)
- Rewriting the whole file from scratch when one line is wrong. Make the targeted fix.
- Probing an unfamiliar API by trial-and-error for many steps — `vault_search` this playbook
  for a working skeleton first (that's what it's for).
- Declaring "done" while the self-test is still red. It's not done until it exits 0.
