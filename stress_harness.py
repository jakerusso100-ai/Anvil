"""Stress harness — drive the Anvil agent on a task with ZERO human intervention,
acting as a non-coder user. Logs every step, auto-approves tools, records what
worked and what broke. Used to find bugs/rough-edges by real usage.

Usage: py -3.14 stress_harness.py <task_id> <model|auto> [reviewer|none]
Tasks are defined in STRESS_TASKS below (naive-user phrasing, no code terms).
Pass a reviewer model (e.g. claude-haiku-4-5) as the 3rd arg to run the build
through the paid-review + auto-fix loop, exactly like Anvil does with the toggle on.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))
import agent  # noqa: E402
import copilot  # noqa: E402

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
    "todo_app": (
        "build me a little to-do list app with a window where i can type a task, hit add, "
        "and see it in a list. i want to be able to check things off and delete them, and "
        "it should remember my tasks when i close and reopen it. make it look clean and "
        "make sure it runs without errors."
    ),
}


def main():
    task_id = sys.argv[1] if len(sys.argv) > 1 else "3d_game"
    model_arg = sys.argv[2] if len(sys.argv) > 2 else "auto"
    reviewer = sys.argv[3] if len(sys.argv) > 3 else "none"
    checker = sys.argv[4] if len(sys.argv) > 4 else "none"  # 4th arg -> quality squad
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
            checker_model=checker, review=(reviewer != "none"), reviewer=reviewer)
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
                               or str(ev.get("stage", "")).startswith("quality-check")):
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
