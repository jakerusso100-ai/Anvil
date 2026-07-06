# Writing a build that passes Anvil's review

Anvil gates every build: it passes only if the build **finished cleanly AND its own
self-test exited 0**. A paid reviewer also reads the files for completeness. Here's how
to clear both.

## The gate (what actually decides pass/fail)
1. Your last **test command** (unittest / pytest / `--selftest`) must exit **0**. A crash,
   timeout, step-limit, or red test = NOT passed. Don't declare "done" while the test is red.
2. Trailing debug commands don't count — the gate looks at your last real *test* run, so
   finish by running the self-test, not by poking at a REPL.
3. If it fails, you get the error fed back — fix the code and re-run the test until green.

## The reviewer (what it looks for)
- A COMPLETE, runnable program — no stubs, no `TODO`, no lone `requirements.txt`.
- Functionality that matches the request. Missing features = "revise".
- It reads your files + the self-test result; it does NOT run the code itself, so a green
  self-test is your proof.

## Checklist before you say "done"
- [ ] Wrote a headless `--selftest` (see [[Headless self-test for games]]) that asserts real behavior.
- [ ] Ran it with `python file.py --selftest` and saw **exit 0**.
- [ ] Installed deps with `python -m pip install ...` (see [[Python on Windows - python not python3]]).
- [ ] Used a proven library for hard logic instead of hand-rolling it.
- [ ] No placeholders — every feature the user asked for is actually implemented.

## Don't burn steps
If you're using an unfamiliar library, `vault_search` this playbook for a skeleton FIRST
(e.g. [[Panda3D first-person walking sim]], [[pygame game template]]). Blindly probing an
API for many steps is how builds time out with nothing written.
