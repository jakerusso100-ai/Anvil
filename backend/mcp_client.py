"""MCP client — connect Anvil's agent to Model Context Protocol servers.

Config: ~/.anvil/mcp.json  →  {"servers": {"<name>": {"command": "...", "args": [...], "env": {}}}}
Servers run over stdio on a dedicated asyncio thread; their tools are exposed to
the agent as `mcp_<server>_<tool>` alongside the built-in tools.
"""
from __future__ import annotations

import asyncio
import json
import threading
from contextlib import AsyncExitStack
from pathlib import Path

CONFIG_PATH = Path.home() / ".anvil" / "mcp.json"
CALL_TIMEOUT = 60

_loop: asyncio.AbstractEventLoop | None = None
_stack: AsyncExitStack | None = None
_sessions: dict[str, object] = {}          # server name -> ClientSession
_registry: dict[str, dict] = {}            # tool spec name -> {server, tool, spec}
_errors: dict[str, str] = {}
_started = False


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True, name="anvil-mcp").start()
    return _loop


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("servers", {})
    except FileNotFoundError:
        return {}
    except Exception as e:
        _errors["<config>"] = f"mcp.json unreadable: {e}"
        return {}


async def _connect(name: str, cfg: dict):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []),
                                   env=cfg.get("env") or None)
    read, write = await _stack.enter_async_context(stdio_client(params))
    session = await _stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    tools = await session.list_tools()
    _sessions[name] = session
    for t in tools.tools:
        spec_name = f"mcp_{name}_{t.name}"[:64]
        _registry[spec_name] = {
            "server": name, "tool": t.name,
            "spec": {"name": spec_name,
                     "description": f"[MCP:{name}] {t.description or t.name}",
                     "parameters": t.inputSchema or {"type": "object", "properties": {}}},
        }


async def _start_all(servers: dict):
    global _stack
    _stack = AsyncExitStack()
    for name, cfg in servers.items():
        try:
            await asyncio.wait_for(_connect(name, cfg), timeout=30)
        except Exception as e:
            _errors[name] = f"{type(e).__name__}: {e}"


def start(force: bool = False) -> None:
    """Idempotent startup; call at app launch or after editing mcp.json."""
    global _started, _sessions, _registry, _errors
    if _started and not force:
        return
    servers = load_config()
    _started = True
    if not servers:
        return
    if force:
        _sessions, _registry = {}, {}
        _errors = {k: v for k, v in _errors.items() if k == "<config>"}
    loop = _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(_start_all(servers), loop)
    try:
        fut.result(timeout=45)
    except Exception as e:
        _errors["<startup>"] = f"{type(e).__name__}: {e}"


def specs() -> list[dict]:
    return [r["spec"] for r in _registry.values()]


def is_mcp_tool(name: str) -> bool:
    return name in _registry


def call(name: str, args: dict) -> str:
    entry = _registry.get(name)
    if not entry:
        return f"ERROR: unknown MCP tool {name}"
    session = _sessions.get(entry["server"])
    if not session:
        return f"ERROR: MCP server {entry['server']} not connected"

    async def _do():
        return await session.call_tool(entry["tool"], args or {})

    try:
        fut = asyncio.run_coroutine_threadsafe(_do(), _ensure_loop())
        result = fut.result(timeout=CALL_TIMEOUT)
    except Exception as e:
        return f"ERROR: MCP call failed: {type(e).__name__}: {e}"
    parts = []
    for c in result.content:
        if getattr(c, "type", "") == "text":
            parts.append(c.text)
        else:
            parts.append(str(c))
    out = "\n".join(parts) or "(empty result)"
    return out[:30_000]


def status() -> dict:
    return {"servers": sorted(_sessions), "tools": len(_registry), "errors": dict(_errors)}
