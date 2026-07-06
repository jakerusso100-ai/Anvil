# Anvil Coding Playbook

A knowledge base for local coding models (gpt-oss, qwen, etc.) running in Anvil.
**Before building anything non-trivial, `vault_search` this vault** for the library, task,
or error you're dealing with — these notes hold correct, working patterns and the mistakes
to avoid, so you don't burn steps rediscovering (or getting wrong) an unfamiliar API.

## Golden rules (apply to EVERY build)
1. **Always add a headless `--selftest`** that runs a few frames/steps and exits 0. A build
   "passes" only if its self-test is actually green. → [[Headless self-test for games]]
2. **Use `python`, not `python3`** on Windows; install with `python -m pip install X`. → [[Python on Windows - python not python3]]
3. **Prefer a proven library** over hand-rolling hard logic (chess rules, 3D physics, parsing). Search this vault first.
4. **Don't trial-and-error an unfamiliar API for many steps** — look up a skeleton here, adapt it, verify.
5. **No stubs / TODOs / placeholders** — finish it, then prove it with the self-test. → [[Writing a build that passes review]]
6. **When a test fails, debug methodically** — read the traceback, reproduce minimally, fix the cause. → [[Debugging systematically]]

## Games & 3D
- [[Headless self-test for games]] — test a game WITHOUT opening a window (the #1 thing that hangs builds)
- [[pygame game template]] — clean 2D game loop + `--selftest`
- [[Raycasting pseudo-3D engine]] — first-person "3D" in pure pygame (mazes, corridors)
- [[Panda3D first-person walking sim]] — real 3D + Bullet physics + NPCs
- [[Ursina 3D engine (easy 3D)]] — the easy path to real 3D (built-in first-person controller)
- [[Collision detection and response]] — AABB/circle, wall sliding, gravity/platforms
- [[A-star pathfinding for NPCs]] — smart NPC/enemy navigation
- [[Procedural generation - mazes and dungeons]] — generate solvable levels
- [[3D vector and matrix math]] — cameras, projection, rotation from scratch

## Web & Apps
- [[Flask web app with SQLite]] — routes + templates + persistent DB
- [[FastAPI REST API]] — typed JSON API, testable in-process
- [[Tkinter desktop app with persistence]] — stdlib GUI + JSON save
- [[CLI apps and consuming APIs]] — argparse + requests

## Algorithms & AI
- [[Minimax and alpha-beta game AI]] — opponents for turn-based games
- [[Recursion and dynamic programming]] — memoize/table patterns
- [[Writing a small interpreter or parser]] — calculators, mini-languages
- [[Data structures, sorting, searching]] — pick the right structure; BFS/DFS/heaps
- [[Chess in Python - use python-chess]] — never hand-roll chess rules

## Python craft
- [[Project structure and clean models]] — layout, dataclasses, type hints
- [[Saving and loading data]] — JSON / SQLite / pickle persistence
- [[Error handling and robustness]] — handle the unhappy path; avoid foot-guns
- [[Testing with pytest and unittest]] — tests that actually run and assert
- [[Debugging systematically]] — the loop that beats flailing
- [[Writing a build that passes review]] — what Anvil's gate + reviewer check

## Other languages (with skeletons + the test command Anvil's gate needs)
- [[Node.js and TypeScript]] — package.json + `npm test`, ESM/CJS, built-in test runner
- [[Rust and cargo]] — cargo project + `cargo test`, Result/? error handling, the borrow checker
- [[Go programs]] — go.mod + `go test ./...`, error handling, gofmt
- [[C-sharp and dotnet]] — `dotnet new` + `dotnet test`, top-level statements

## Other ecosystems (not Python)
- [[Minecraft Fabric mod (Java Gradle)]] — mod structure; check for a JDK first
- [[Godot and GDScript basics]] — engine + GDScript patterns

*Add more notes here for any library or task the models keep getting wrong — keyword-rich
titles + bodies make them findable via `vault_search`.*
