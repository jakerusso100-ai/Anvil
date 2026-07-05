"""Anvil test suite — backend units, security, GUI headless, event-flow simulation.

Run: py -3.14 -X utf8 anvil/tests/test_anvil.py
No Ollama calls (benchmarks may own it); model tests use mocks or Anthropic Haiku.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PASS, FAIL = 0, []


def check(name: str, fn):
    global PASS
    try:
        fn()
        PASS += 1
        print(f"  ok    {name}")
    except Exception as e:
        FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")
        if os.environ.get("ANVIL_TEST_TRACE"):
            traceback.print_exc()


def expect(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "expectation failed")


# ================= tools.py =================

def test_tools():
    import tools
    ws = tempfile.mkdtemp(prefix="anvil_t_")

    check("write_file creates", lambda: expect(
        "wrote" in tools.run_tool("write_file", {"path": "a/b.py", "content": "x = 1\n"}, ws)
        and (Path(ws) / "a/b.py").exists()))
    check("read_file numbers lines", lambda: expect(
        "1| x = 1" in tools.run_tool("read_file", {"path": "a/b.py"}, ws)))
    check("edit_file exact replace", lambda: expect(
        "edited" in tools.run_tool("edit_file", {"path": "a/b.py", "old_text": "x = 1", "new_text": "x = 2"}, ws)))
    check("edit_file missing text -> error", lambda: expect(
        "not found" in tools.run_tool("edit_file", {"path": "a/b.py", "old_text": "zzz", "new_text": "y"}, ws)))
    check("edit_file ambiguous -> error", lambda: (
        tools.run_tool("write_file", {"path": "dup.txt", "content": "aa\naa\n"}, ws),
        expect("2 times" in tools.run_tool("edit_file", {"path": "dup.txt", "old_text": "aa", "new_text": "b"}, ws))))
    check("list_dir works", lambda: expect(
        "b.py" in tools.run_tool("list_dir", {"path": "a"}, ws)))
    check("bash runs in workspace", lambda: expect(
        "[exit 0]" in tools.run_tool("bash", {"command": "echo hello"}, ws)))
    check("bash bad exit reported", lambda: expect(
        "[exit" in tools.run_tool("bash", {"command": "exit 3"}, ws)))
    # security: escape attempts must be rejected
    check("path traversal blocked (..)", lambda: expect(
        "ERROR" in tools.run_tool("read_file", {"path": "../../windows/win.ini"}, ws)))
    check("path traversal blocked (abs)", lambda: expect(
        "ERROR" in tools.run_tool("read_file", {"path": "C:/Windows/win.ini"}, ws)))
    check("huge output truncated", lambda: (
        tools.run_tool("write_file", {"path": "big.txt", "content": "z" * 100_000}, ws),
        expect(len(tools.run_tool("read_file", {"path": "big.txt"}, ws)) <= tools.MAX_TOOL_RESULT + 100)))
    check("unknown tool -> error", lambda: expect(
        "unknown tool" in tools.run_tool("nope", {}, ws)))


# ================= agent checkpoints =================

def test_checkpoints():
    import agent
    ws = tempfile.mkdtemp(prefix="anvil_c_")
    f = Path(ws) / "code.py"
    f.write_text("v1", encoding="utf-8")

    def flow():
        r, denied, diff = agent._exec_tool("write_file", {"path": "code.py", "content": "v2"},
                                           ws, "run1", lambda n, a: True)
        expect(not denied and diff and diff["before"] == "v1" and diff["after"] == "v2", "diff wrong")
        expect(f.read_text(encoding="utf-8") == "v2")
        agent.restore_file(ws, "run1", "code.py")
        expect(f.read_text(encoding="utf-8") == "v1", "restore_file failed")
    check("edit -> diff -> single-file revert", flow)

    def new_file_flow():
        r, d, diff = agent._exec_tool("write_file", {"path": "new.py", "content": "n"},
                                      ws, "run2", lambda n, a: True)
        expect((Path(ws) / "new.py").exists())
        agent.restore_file(ws, "run2", "new.py")
        expect(not (Path(ws) / "new.py").exists(), "new file should be deleted on reject")
    check("reject newly-created file deletes it", new_file_flow)

    def deny_flow():
        r, denied, diff = agent._exec_tool("bash", {"command": "echo x"}, ws, "run3",
                                           lambda n, a: False)
        expect(denied and diff is None and "denied" in r.lower())
    check("approval denial path", deny_flow)

    def restore_all():
        (Path(ws) / "m1.txt").write_text("orig1", encoding="utf-8")
        agent._exec_tool("write_file", {"path": "m1.txt", "content": "mod1"}, ws, "run4", lambda n, a: True)
        agent._exec_tool("write_file", {"path": "m2.txt", "content": "mod2"}, ws, "run4", lambda n, a: True)
        restored = agent.restore_checkpoint(ws, "run4")
        expect((Path(ws) / "m1.txt").read_text(encoding="utf-8") == "orig1", "m1 not restored")
        expect("m1.txt" in " ".join(restored))
    check("restore whole checkpoint", restore_all)


# ================= llm helpers =================

def test_llm():
    import llm
    check("remote_provider_for parses", lambda: expect(
        llm.remote_provider_for("or/z-ai/glm-5.1")[1] == "z-ai/glm-5.1"))
    check("remote_provider_for rejects others", lambda: expect(
        llm.remote_provider_for("gpt-oss:20b") is None))
    check("is_api_model", lambda: expect(
        llm.is_api_model("claude-opus-4-8") and not llm.is_api_model("or/x") and not llm.is_api_model("gpt-oss:20b")))
    check("looks_like_code gate", lambda: expect(
        llm.looks_like_code("```python\nx\n```") and not llm.looks_like_code("just chat about weather")))
    check("remote list has GLM + MiniMax", lambda: expect(
        {"or/z-ai/glm-5.1", "or/minimax/minimax-m2.5"} <=
        {r["spec"] for r in llm.list_remote_models()}))

    def no_key_raises():
        try:
            list(llm.stream_chat("or/z-ai/glm-5.1", [{"role": "user", "content": "x"}]))
            expect(False, "should raise without key")
        except RuntimeError as e:
            expect("OPENROUTER_API_KEY" in str(e))
    if not os.environ.get("OPENROUTER_API_KEY"):
        check("remote without key -> clean error", no_key_raises)


# ================= copilot =================

def test_copilot():
    import copilot
    check("fallback skips failed model", lambda: expect(
        copilot.fallback_for("gpt-oss:20b") != "gpt-oss:20b"))
    check("fallback local-only mode", lambda: expect(
        not str(copilot.fallback_for("qwen3-coder:30b", allow_api=False)).startswith("claude")))
    check("route map covers all categories", lambda: expect(
        set(copilot.ROUTE_TO_ROSTER) >= {"quick_question", "small_code", "build_app",
                                          "refactor_multi_file", "hard_reasoning", "image_task"}))

    def dead_router():
        import llm
        old = llm.OLLAMA_URL
        llm.OLLAMA_URL = "http://localhost:1"  # nothing listens here
        try:
            r = copilot.route("write me a game", router_model="whatever")
            expect(r["model"] and not r["router_ok"], "should degrade gracefully")
        finally:
            llm.OLLAMA_URL = old
    check("router down -> graceful default", dead_router)

    check("health returns all components", lambda: expect(
        {"Ollama", "Roster", "API"} <= {h["name"] for h in copilot.health()}))


# ================= GUI headless =================

def test_gui():
    from PySide6.QtWidgets import QApplication
    import importlib
    main = importlib.import_module("main")
    app = QApplication.instance() or QApplication([])
    w = main.Main()

    check("perm modes present", lambda: expect(
        [w.perm.itemText(i) for i in range(w.perm.count())] == ["Ask", "Accept edits", "Plan", "Bypass"]))
    check("auto is default coder", lambda: expect(w.coder.currentData() == main.AUTO))

    ws = tempfile.mkdtemp(prefix="anvil_g_")
    (Path(ws) / "hello.py").write_text("print(1)\n", encoding="utf-8")
    w.workspace = ws
    w.index_workspace()
    check("workspace indexing", lambda: expect("hello.py" in w.ws_files))
    check("mention expansion", lambda: expect(
        "<file path=" in w.expand_mentions("look at @hello.py please")))
    check("mention of missing file unchanged", lambda: expect(
        w.expand_mentions("@nope.py") == "@nope.py"))

    # simulated event stream — the UI must survive every event type in order
    def storm():
        w.bubbles = {}
        events = [
            {"type": "run_started", "run_id": "r1"},
            {"type": "routed", "model": "gpt-oss:20b", "category": "small_code", "why": "test"},
            {"type": "stage", "stage": "thinking", "model": "gpt-oss:20b", "step": 1},
            {"type": "delta", "channel": "agent", "round": 0, "text": "hello **md** `code`"},
            {"type": "tool_call", "name": "bash", "args": {"command": "echo hi"}},
            {"type": "tool_result", "name": "bash", "output": "[exit 0]\nhi", "denied": False,
             "diff": None, "run_id": "r1"},
            {"type": "tool_call", "name": "write_file", "args": {"path": "hello.py", "content": "print(2)"}},
            {"type": "tool_result", "name": "write_file", "output": "wrote 8 chars", "denied": False,
             "diff": {"path": "hello.py", "before": "print(1)\n", "after": "print(2)"}, "run_id": "r1"},
            {"type": "tool_call", "name": "bash", "args": {"command": "big"}},
            {"type": "tool_result", "name": "bash", "output": "y" * 2000, "denied": False,
             "diff": None, "run_id": "r1"},
            {"type": "redirect", "from": "a", "to": "b", "error": "boom"},
            {"type": "review", "round": 1, "verdict": "revise", "summary": "s",
             "issues": [{"severity": "major", "problem": "p", "fix": "f"}],
             "reviewer": "claude-haiku-4-5", "cost": 0.001},
            {"type": "stage", "stage": "revising", "model": "m", "round": 1},
            {"type": "delta", "channel": "revision", "round": 1, "text": "fixed"},
            {"type": "review_error", "error": "x"},
            {"type": "final_text", "answer": "done"},
            {"type": "final", "cost": 0.002, "reviewed": True, "revised": True, "passed": True,
             "answer": "", "run_id": "r1"},
        ]
        for ev in events:
            w.on_event(ev)
    check("event storm survives", storm)

    check("slash /help", lambda: expect(w.slash("/help") is True))
    check("slash /clear resets", lambda: (w.history.append({"role": "user", "content": "x"}),
                                          w.slash("/clear"), expect(w.history == [])))
    check("ctx meter formats", lambda: (w.history.append({"role": "user", "content": "x" * 8000}),
                                        w.update_ctx_meter(),
                                        expect("2,000" in w.ctx_lbl.text())))

    # DiffCard reject must actually revert
    def diff_reject():
        import agent
        f = Path(ws) / "hello.py"
        f.write_text("orig", encoding="utf-8")
        agent._checkpoint(ws, "rX", "hello.py")
        f.write_text("changed", encoding="utf-8")
        dc = main.DiffCard("hello.py", "orig", "changed", ws, "rX")
        dc._reject()
        expect(f.read_text(encoding="utf-8") == "orig", "reject did not revert")
    check("DiffCard reject reverts file", diff_reject)

    # worker approval logic (no thread start needed)
    def perms():
        wk = main.Worker("agent", {"model": "m"}, "Plan", "r", True, "t", ws)
        expect(wk.approve("bash", {"command": "x"}) is False, "plan must deny")
        wk2 = main.Worker("agent", {"model": "m"}, "Bypass", "r", True, "t", ws)
        expect(wk2.approve("bash", {"command": "x"}) is True, "bypass must allow")
        wk3 = main.Worker("agent", {"model": "m"}, "Accept edits", "r", True, "t", ws)
        expect(wk3.approve("write_file", {"path": "p", "content": "c"}) is True,
               "accept-edits must allow edits")
    check("permission mode logic", perms)

    def diff_preview():
        wk = main.Worker("agent", {"model": "m"}, "Ask", "r", True, "t", ws)
        (Path(ws) / "pv.py").write_text("a\nb\n", encoding="utf-8")
        d = wk._diff_preview("write_file", {"path": "pv.py", "content": "a\nc\n"})
        expect("+c" in d and "-b" in d, f"diff preview wrong: {d[:100]}")
    check("ask-mode diff preview", diff_preview)


def run_all():
    print("== tools =="); test_tools()
    print("== checkpoints =="); test_checkpoints()
    print("== llm =="); test_llm()
    print("== copilot =="); test_copilot()
    print("== gui =="); test_gui()
    print(f"\n{PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    return len(FAIL)


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
