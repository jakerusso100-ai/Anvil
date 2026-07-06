"""Stress harness — drive the Anvil agent on a task with ZERO human intervention,
acting as a non-coder user. Logs every step, auto-approves tools, records what
worked and what broke. Used to find bugs/rough-edges by real usage.

Usage: py -3.14 stress_harness.py <task_id> <model|auto> [reviewer|none]
Tasks are defined in STRESS_TASKS below (naive-user phrasing, no code terms).
Pass a reviewer model (e.g. claude-haiku-4-5) as the 3rd arg to run the build
through the paid-review + auto-fix loop, exactly like Anvil does with the toggle on.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))
import agent  # noqa: E402
import copilot  # noqa: E402
import tools  # noqa: E402

# Connect an Obsidian vault so the models can vault_search it for reference/correction.
_VAULT = os.environ.get("ANVIL_VAULT")
if _VAULT:
    tools.VAULT_PATH = _VAULT
    print(f"[vault] connected — models can vault_search: {_VAULT}")

STRESS_TASKS = {
    "3d_game": (
        "make me a 3d game in python where i can walk around in first person inside a "
        "maze and find my way out. i should be able to look around with the arrow keys "
        "and move with WASD. make the walls look 3d with some kind of shading so it feels "
        "like im really there. put a goal or exit somewhere in the maze that says i won "
        "when i reach it. make it actually run and look 3d, fully finished please, and "
        "make sure it works before telling me it's done."
    ),
    "minecraft_mod": (
        "i want a simple minecraft-like block building game in python. i should see a 3d "
        "world made of blocks that i can walk around in, and be able to place and remove "
        "blocks by clicking. like a tiny version of minecraft creative mode. make the "
        "ground out of grass blocks and let me build stuff on top. make it run and "
        "actually work, completely finished, and test it yourself first."
    ),
    "3d_space_flight": (
        "make me a 3d space flying game in python. i want to be in a cockpit flying "
        "through space in first person, and there should be asteroids or obstacles coming "
        "at me that get bigger as they get closer so it looks 3d, and i steer left and "
        "right and up and down with the arrow keys to dodge them. keep score for how long "
        "i survive or how many i dodge. make it feel fast and 3d and actually run. test it "
        "yourself and make sure it works 100% before saying it's done."
    ),
    "roguelike": (
        "make me a dungeon crawler game in python where i explore rooms full of "
        "monsters, pick up items and weapons, and fight my way deeper level by level. "
        "i want an inventory i can open, health that goes down when a monster hits me, "
        "and different monsters that behave differently. it should save my game so i can "
        "quit and come back to the same spot later. make it actually run and be playable "
        "the whole way through, fully finished, and test it yourself before saying it's done."
    ),
    "chess_ai": (
        "make me a chess game in python that i can play against the computer. i want to "
        "see the board, move my pieces, and the computer should play real legal moves "
        "back and actually try to beat me, not move randomly. all the chess rules need to "
        "work - castling, en passant, checkmate, the works. make it actually run and be "
        "playable, and test it yourself to make sure the moves are legal before telling me "
        "it's done."
    ),
    "fabric_mod": (
        "i want a real minecraft mod that adds a new item to the game. make it a proper "
        "mod i could actually load into minecraft with fabric - set up all the files and "
        "folders it needs, write the java code, the mod metadata, everything from scratch. "
        "i'm not a coder so do the whole project setup yourself and make sure it builds "
        "with no errors. check it yourself before saying it's finished."
    ),
    "walking_sim": (
        "make me a fully finished 3d first person walking simulator game in python. i want "
        "to walk around inside a 3d world in first person — move with WASD and look around "
        "with the mouse. it needs real physics so i can't walk through walls and there's "
        "gravity so i stay on the ground. put some NPCs (people or creatures) in the world "
        "that wander around on their own so it feels alive. make the world feel like a real "
        "3d space to explore with some objects in it. make it actually run and be fully "
        "playable, and test it yourself HEADLESSLY (a --selftest that steps a few frames and "
        "exits) to make sure it works before telling me it's done."
    ),
    "walking_sim2": (
        "make me a fully finished 3d first person walking simulator game in python. i want "
        "to walk around inside a 3d world in first person — move with WASD and look around "
        "with the mouse. it needs real physics so i can't walk through walls and there's "
        "gravity so i stay on the ground. put some NPCs (people or creatures) in the world "
        "that wander around on their own so it feels alive. make the world feel like a real "
        "3d space to explore with some objects in it. make it actually run and be fully "
        "playable, and test it yourself HEADLESSLY (a --selftest that steps a few frames and "
        "exits) to make sure it works before telling me it's done."
    ),
    "node_cli": (
        "make me a command-line tool in node.js (javascript) called wordcount. i run it "
        "like `node wordcount.js some text here` and it prints each unique word with how "
        "many times it appears, sorted from most to least common. include a package.json "
        "and a test i can run with `npm test` that proves it works. make it actually run "
        "and test it yourself before saying it's done."
    ),
    "raytracer": (
        "make me a ray tracer in python from scratch — no graphics engines, just math and "
        "pillow to save the image. render a 3d scene with several spheres of different "
        "colors and materials (some shiny and reflective, some matte) sitting on a "
        "checkered floor, lit by at least two lights so there are real shadows. add "
        "reflections so the shiny spheres mirror the scene, and anti-aliasing so edges are "
        "smooth. save the result as a PNG. it must actually run and produce a real rendered "
        "3d image. test it yourself HEADLESSLY: render a small image, assert the PNG exists "
        "and isn't blank, and use visual_check to confirm it looks like a lit 3d scene with "
        "spheres and shadows — before telling me it's done."
    ),
    "java_cli": (
        "make me a small command-line program in java. it should be able to check if a "
        "word is a palindrome (like 'racecar') and also print the first N fibonacci "
        "numbers. i'm not a coder, so create the whole thing, write the java code, and make "
        "it compile and run with javac then java — no build tools like maven or gradle, just "
        "plain java files. include a headless self-test (a main path or method that runs "
        "known cases: racecar->palindrome, hello->not, fib(7)->0 1 1 2 3 5 8) that prints "
        "ALL TESTS PASSED and exits 0, or exits non-zero if anything is wrong. compile it "
        "and RUN that self-test yourself to prove it works before telling me it's done."
    ),
    "todo_app": (
        "build me a little to-do list app with a window where i can type a task, hit add, "
        "and see it in a list. i want to be able to check things off and delete them, and "
        "it should remember my tasks when i close and reopen it. make it look clean and "
        "make sure it runs without errors."
    ),
}


def main():
    # Console may be cp1252 (Windows); a model's answer can contain chars it can't encode
    # (e.g. a non-breaking hyphen), which would crash the final print AFTER a good build.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    task_id = sys.argv[1] if len(sys.argv) > 1 else "3d_game"
    model_arg = sys.argv[2] if len(sys.argv) > 2 else "auto"
    reviewer = sys.argv[3] if len(sys.argv) > 3 else "none"
    checker = sys.argv[4] if len(sys.argv) > 4 else "none"  # 4th arg -> quality squad
    escalate = sys.argv[5] if len(sys.argv) > 5 else "none"  # 5th arg -> paid last-mile fix
    prompt = STRESS_TASKS[task_id]
    ws = Path(__file__).parent / "examples" / f"stress_{task_id}"
    ws.mkdir(parents=True, exist_ok=True)

    if model_arg == "auto":
        r = copilot.route(prompt, allow_api=False)  # non-coder wouldn't have API set up
        model = r["model"]
        print(f"[copilot] routed '{r['category']}' -> {model}  ({r['why']})")
    else:
        model = model_arg

    review_note = f" · reviewer={reviewer}" if reviewer != "none" else " · local-only"
    squad_note = f" · squad-checker={checker}" if checker != "none" else ""
    print(f"=== STRESS: {task_id} · model={model}{review_note}{squad_note} ===\n")
    t0 = time.perf_counter()
    steps = tool_calls = errors = 0
    files = set()
    last_answer = ""
    msg = [{"role": "user", "content": prompt}]
    if checker != "none":
        stream = agent.run_agent_squad(
            model, msg, str(ws), approve=lambda n, a: True,
            checker_model=checker, review=(reviewer != "none"), reviewer=reviewer,
            escalate_to=(escalate if escalate != "none" else None))
    elif reviewer != "none":
        stream = agent.run_agent_reviewed(
            model, msg, str(ws), approve=lambda n, a: True,
            review=True, reviewer=reviewer, auto_revise=True, max_rounds=2)
    else:
        stream = agent.run_agent(model, msg, str(ws), approve=lambda n, a: True)
    for ev in stream:
        t = ev["type"]
        if t == "stage" and ev.get("step"):
            steps = ev["step"]
            print(f"[step {steps}] {ev['stage']} ({ev['model']})", flush=True)
        elif t == "tool_call":
            tool_calls += 1
            args = {k: (str(v)[:50]) for k, v in (ev["args"] or {}).items()}
            print(f"  [TOOL] {ev['name']}: {args}", flush=True)
            if ev["name"] in ("write_file", "edit_file") and ev["args"].get("path"):
                files.add(ev["args"]["path"])
        elif t == "tool_result":
            out = (ev["output"] or "")[:120].replace("\n", " | ")
            if "ERROR" in ev["output"] or "Traceback" in ev["output"] or "timed out" in ev["output"]:
                errors += 1
            print(f"        -> {out}", flush=True)
        elif t == "stage" and (ev.get("stage") == "building"
                               or str(ev.get("stage", "")).startswith("quality-check")
                               or str(ev.get("stage", "")).startswith("escalate")):
            print(f"\n[SQUAD] === {ev['stage']} ({ev['model']}) ===", flush=True)
        elif t == "stage" and ev.get("stage") == "reviewing":
            print(f"[REVIEW] {ev['model']} inspecting the build (round {ev['round']})...", flush=True)
        elif t == "review":
            print(f"[REVIEW] verdict={ev['verdict'].upper()} · {len(ev['issues'])} issues · "
                  f"${ev['cost']} · {ev['summary'][:90]}", flush=True)
            for i in ev["issues"][:6]:
                print(f"         - [{i['severity']}] {i['problem'][:90]}", flush=True)
        elif t == "review_error":
            print(f"[REVIEW] error: {ev['error']}", flush=True)
        elif t == "final":
            if ev.get("reviewed"):
                verdict = "PASSED" if ev.get("passed") else ("still-had-issues" if ev.get("revised") else "n/a")
                print(f"[REVIEW] final: reviewed=True revised={ev.get('revised')} -> {verdict}", flush=True)
        elif t == "final_text":
            last_answer = ev.get("answer") or ""

    dt = time.perf_counter() - t0
    build_fail = agent._agent_failed(last_answer)
    status = f"BUILD FAILED ({build_fail})" if build_fail else "build finished"
    print(f"\n=== DONE in {dt:.0f}s · {steps} steps · {tool_calls} tool calls · "
          f"{errors} error-results · {status} · files: {sorted(files)} ===")
    print(f"=== FINAL MESSAGE:\n{last_answer[:600]}")


if __name__ == "__main__":
    main()
