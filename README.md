# Anvil — local AI coding studio

A native desktop coding assistant (like Cursor + Claude Code) that runs **local
models** for most work and escalates to paid API models only when it helps —
with a built-in quality-review pipeline neither of those tools has.

No browser, no Electron. Single-file `Anvil.exe`, or run from source.

## Run

```powershell
# from source
py -3.14 desktop/main.py

# or the standalone binary
dist\Anvil.exe
```

Set `ANTHROPIC_API_KEY` (optional — enables the paid reviewer and API models).
Ollama must be running for local models.

## What it does

- **Agent mode** — the model uses tools: read/write/edit files, run commands,
  web search + fetch, semantic codebase search, project memory, subagents,
  Obsidian vault, and any MCP server. Permission modes (Ask / Accept edits /
  Plan / Bypass) with diff-preview approvals and one-click revert.
- **Chat mode** — a local model writes code, a paid model reviews it, and the
  local model auto-fixes using the reviewer's guidance (all optional/toggleable).
- **Auto (copilot) routing** — a small fast local model classifies each request
  and picks the right specialist; redirects on failure; health monitoring.
- **Editor** — file tree, tabs, syntax highlighting, tab-autocomplete (FIM),
  live-sync when the agent edits an open file, and an integrated terminal.
- **Sessions** persist and resume across restarts.

See `FEATURES.md` for the full parity matrix.

## Layout

| Path | What |
|---|---|
| `backend/` | agent loop, tools, model adapters, copilot router, semantic index, MCP, sessions |
| `desktop/` | PySide6 GUI + shared pipeline |
| `tests/`   | 94-test suite (units, security, GUI, agent protocol, guards) |
| `dist/`    | standalone `Anvil.exe` |
| `examples/`| a space game an Anvil agent built end-to-end from a non-coder prompt |

## Model roster (benchmarked)

Chosen by a benchmark suite, not by vibes:

| Role | Model |
|---|---|
| Fast daily coding | `gpt-oss:20b` |
| Whole-app building | `qwen3-coder-next` |
| Vision | `qwen3-vl:8b` |
| Copilot router | `granite4` |
| Tab autocomplete | `qwen2.5-coder` |
| Semantic search | `nomic-embed-text` |
| Paid escalation | Haiku → Sonnet → Opus / Fable |

## Tests

```powershell
for %t in (test_anvil test_round2 test_round3 test_round4 test_round5 test_round6) do py -3.14 tests\%t.py
```
