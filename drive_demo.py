"""Drive Anvil's agent exactly as the GUI Send button does (Agent mode, Bypass perms),
on a real complicated task, logging every tool call so we can see it work."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "backend"))
import agent, copilot

WS = r"C:/Users/jaker/OneDrive/Documentos/jarvis/anvil_demo_game"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gpt-oss:20b"

# A real non-coder's prompt: they describe what they WANT, in plain words, with no
# technical terms, and expect it to just work. No mention of files, tests, or how.
PROMPT = """i want you to make me a really cool space game in python that i can actually \
play. it should be like asteroids but way better. my spaceship should be in the middle and \
i fly it around with the arrow keys and shoot lasers with the spacebar. there should be \
asteroids floating around and when i shoot them they break into smaller pieces and then \
disappear, and i get points for hitting them. if an asteroid hits my ship i lose a life, \
and i start with 3 lives. show my score and lives on the screen. when i run out of lives \
it should say game over and let me press a key to play again. make it look nice with the \
ship and asteroids actually drawn as shapes, and add little enemy ufos that fly in \
sometimes and shoot at me for extra challenge. i want it to be smooth and fun and actually \
work when i run it, 100% finished, not half done. please make sure it runs without any \
errors before you tell me it's ready."""


def main():
    log = Path(WS) / "_agent_run.log"
    t0 = time.time()
    steps = tools_used = 0
    diffs = []
    with open(log, "w", encoding="utf-8") as f:
        def w(s):
            print(s, flush=True); f.write(s + "\n"); f.flush()
        # Faithful to the app's default "Auto" mode: the copilot router picks the model.
        model = MODEL
        if MODEL == "auto":
            r = copilot.route(PROMPT, copilot.DEFAULT_ROUTER, allow_api=False)
            model = r["model"]
            w(f"[copilot] routed '{r['category']}' -> {model}  ({r.get('why','')})")
        w(f"=== Anvil agent · model={model} · task=user's space game ===")
        for ev in agent.run_agent(model, [{"role": "user", "content": PROMPT}], WS,
                                  approve=lambda n, a: True):  # Bypass perms (auto-approve)
            t = ev["type"]
            if t == "stage" and ev.get("step"):
                steps = ev["step"]; w(f"\n[step {ev['step']}] thinking ({ev['model']})")
            elif t == "delta" and ev["channel"] == "agent" and ev.get("text", "").strip():
                w("  » " + ev["text"].strip()[:200])
            elif t == "tool_call":
                tools_used += 1
                a = ev["args"] or {}
                detail = a.get("path") or a.get("command") or a.get("query") or ""
                w(f"  [TOOL] {ev['name']}: {str(detail)[:90]}")
            elif t == "tool_result":
                out = (ev.get("output") or "")[:120].replace("\n", " | ")
                w(f"        -> {out}")
                if ev.get("diff"):
                    diffs.append(ev["diff"]["path"])
            elif t == "final_text":
                w(f"\n[FINAL] {(ev.get('answer') or '')[:400]}")
        dt = time.time() - t0
        w(f"\n=== done in {dt:.0f}s · {steps} steps · {tools_used} tool calls · "
          f"files touched: {sorted(set(diffs))} ===")


if __name__ == "__main__":
    main()
