"""Stress harness — drive the Anvil agent on a task with ZERO human intervention,
acting as a non-coder user. Logs every step, auto-approves tools, records what
worked and what broke. Used to find bugs/rough-edges by real usage.

Usage: py -3.14 stress_harness.py <task_id> <model|auto>
Tasks are defined in STRESS_TASKS below (naive-user phrasing, no code terms).
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
    prompt = STRESS_TASKS[task_id]
    ws = Path(__file__).parent / "examples" / f"stress_{task_id}"
    ws.mkdir(parents=True, exist_ok=True)

    if model_arg == "auto":
        r = copilot.route(prompt, allow_api=False)  # non-coder wouldn't have API set up
        model = r["model"]
        print(f"[copilot] routed '{r['category']}' -> {model}  ({r['why']})")
    else:
        model = model_arg

    print(f"=== STRESS: {task_id} · model={model} ===\n")
    t0 = time.perf_counter()
    steps = tool_calls = errors = 0
    files = set()
    last_answer = ""
    for ev in agent.run_agent(model, [{"role": "user", "content": prompt}], str(ws),
                              approve=lambda n, a: True):
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
        elif t == "final_text":
            last_answer = ev.get("answer") or ""

    dt = time.perf_counter() - t0
    print(f"\n=== DONE in {dt:.0f}s · {steps} steps · {tool_calls} tool calls · "
          f"{errors} error-results · files: {sorted(files)} ===")
    print(f"=== FINAL MESSAGE:\n{last_answer[:600]}")


if __name__ == "__main__":
    main()
