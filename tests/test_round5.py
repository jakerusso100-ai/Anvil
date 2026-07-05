"""Round 5 — auto-memory, hooks, subagents (the tail features), offline.

Run: py -3.14 -X utf8 anvil/tests/test_round5.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import agent  # noqa: E402
import tools  # noqa: E402


def test_memory():
    ws = tempfile.mkdtemp(prefix="anvil_mem_")
    check("remember saves", lambda: expect("saved" in tools.run_tool(
        "remember", {"note": "build with py -3.14"}, ws)))
    check("remember dedups", lambda: (
        tools.run_tool("remember", {"note": "build with py -3.14"}, ws),
        expect((Path(ws) / ".anvil" / "memory.md").read_text(encoding="utf-8").count("build with") == 1)))
    check("memory loads into system prompt", lambda: expect(
        "build with py -3.14" in agent._project_instructions(ws)
        and "past sessions" in agent._project_instructions(ws)))
    check("remember not gated (auto-saves)", lambda: expect(not tools.is_dangerous("remember")))


def test_hooks():
    ws = tempfile.mkdtemp(prefix="anvil_hook_")
    hp = Path.home() / ".anvil" / "hooks.json"
    hp.parent.mkdir(parents=True, exist_ok=True)
    old = hp.read_text(encoding="utf-8") if hp.exists() else None

    def post_edit_fires():
        hp.write_text(json.dumps({"post_edit": "echo HOOKED {path}"}), encoding="utf-8")
        try:
            res, _, _ = agent._exec_tool("write_file", {"path": "a.py", "content": "x"},
                                         ws, "r", lambda n, a: True)
            expect("HOOKED" in res and "a.py" in res, f"hook missing: {res!r}")
        finally:
            hp.unlink()
    check("post_edit hook fires with {path}", post_edit_fires)

    def post_bash_fires():
        hp.write_text(json.dumps({"post_bash": "echo AFTERBASH"}), encoding="utf-8")
        try:
            res, _, _ = agent._exec_tool("bash", {"command": "echo hi"}, ws, "r", lambda n, a: True)
            expect("AFTERBASH" in res, f"bash hook missing: {res!r}")
        finally:
            hp.unlink()
    check("post_bash hook fires", post_bash_fires)

    def no_config_safe():
        if hp.exists():
            hp.unlink()
        expect(agent.run_hooks("post_edit", ws, {"path": "x"}) == "", "no config must be silent")
    check("missing hooks.json is silent", no_config_safe)

    if old is not None:
        hp.write_text(old, encoding="utf-8")


def test_subagent():
    ws = tempfile.mkdtemp(prefix="anvil_sub_")

    def delegate():
        scripted = iter([
            {"content": "", "tool_calls": [{"function": {
                "name": "write_file", "arguments": json.dumps({"path": "s.txt", "content": "sub"})}}]},
            {"content": "done", "tool_calls": []},
        ])
        orig = agent._ollama_step
        agent._ollama_step = lambda m, msgs: next(scripted)
        agent._ACTIVE_MODEL["name"] = "mock"
        try:
            out = agent._run_subagent("write s.txt", "mock", ws, "r", lambda n, a: True, 0)
        finally:
            agent._ollama_step = orig
        expect("subagent completed" in out and (Path(ws) / "s.txt").exists(), out)
    check("subagent runs nested loop + returns summary", delegate)

    check("subagent depth limit", lambda: expect(
        "depth limit" in agent._run_subagent("x", "m", ws, "r", lambda n, a: True, 2)))

    def via_exec_tool():
        scripted = iter([{"content": "ok", "tool_calls": []}])
        orig = agent._ollama_step
        agent._ollama_step = lambda m, msgs: next(scripted)
        agent._ACTIVE_MODEL["name"] = "mock"
        try:
            res, denied, diff = agent._exec_tool("spawn_subagent", {"task": "noop"},
                                                 ws, "r", lambda n, a: True, 0)
        finally:
            agent._ollama_step = orig
        expect("subagent completed" in res and not denied and diff is None)
    check("spawn_subagent via _exec_tool", via_exec_tool)


def test_tool_registry():
    tools.INDEX_READY = True
    names = {t["name"] for t in tools._active_specs()}
    check("new tools registered", lambda: expect(
        {"remember", "spawn_subagent", "codebase_search"} <= names, names))
    check("agent tool schemas valid", lambda: expect(
        all("input_schema" in t for t in tools.anthropic_tools())))


if __name__ == "__main__":
    print("== auto-memory =="); test_memory()
    print("== hooks =="); test_hooks()
    print("== subagents =="); test_subagent()
    print("== registry =="); test_tool_registry()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
