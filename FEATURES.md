# Anvil feature matrix — Claude Code + Cursor parity tracker

Legend: ✅ done · 🔨 this build · 🗓 planned · ➖ not applicable locally

## Core agent (Claude Code)
| Feature | Status | Notes |
|---|---|---|
| Read/write/edit files | ✅ | `tools.py`: read_file, write_file, edit_file (exact-match, confined to workspace) |
| Run shell commands | ✅ | `bash` tool, timeout, workspace cwd |
| List/glob directory | ✅ | list_dir (glob 🗓) |
| Web search + web fetch | ✅ | ddgs + requests — local models get internet like Claude |
| Agentic loop (multi-step tool use) | ✅ | `agent.py`, Ollama native tool calling + Anthropic tool use, 25-step cap |
| Permission modes / approvals | ✅ | auto-approve toggle; dangerous tools (bash/write/edit) prompt when off |
| CLAUDE.md project instructions | ✅ | reads `ANVIL.md` (or CLAUDE.md) from workspace into system prompt |
| Checkpoints / rewind | ✅ | file snapshots to `.anvil/checkpoints/` before agent edits + restore button |
| Slash commands | ✅ | /clear, /help, /model; more 🗓 |
| Quality-review pipeline | ✅ | local coder + paid reviewer + auto-fix loop (Anvil original — neither app has this) |
| Reviewed **builds** (Agent mode) | ✅ | after a local build finishes, a paid reviewer inspects the written files + self-test and loops concrete fixes back into the agent — toggleable, zero human intervention |
| **Quality-check squad** | ✅ | Anvil original — the main model builds, then checker sub-agents (local or paid) inspect the code and directly fix/fill-in what they find, each with a focused lens (runnability, correctness), re-testing as they go |
| **Auto-escalation** | ✅ | if the free local squad still can't get the self-test green, Anvil auto-hands just the last-mile fix to a paid model — free until it genuinely can't finish, then cents |
| **Bundled coding playbook + RAG** | ✅ | 28 correct-pattern notes ship with Anvil and are auto-injected (semantic, nomic-embed) into every build, so local models get expertise on tap with zero setup |
| **Prompt Maker** mode | ✅ | Anvil original — a 3rd mode that interviews you (2D/3D? solo/multiplayer? …) with research-only tools and drafts a polished build prompt, with one-click handoff to the builder |
| Cost/usage tracking | ✅ | per-session cost meter |
| Model routing (local+API) | ✅ | Ollama + LM Studio + Anthropic in one picker |
| Subagents / agent teams | ✅ | `spawn_subagent` tool runs a nested agent loop for a focused subtask, returns a summary (keeps parent context clean); depth-limited to 2 |
| Hooks (pre/post tool) | ✅ | `~/.anvil/hooks.json` → shell commands on `post_edit`/`post_bash` with `{path}`/`{command}` placeholders (auto-format, lint, etc.) |
| Auto memory | ✅ | `remember` tool saves learnings to `.anvil/memory.md`, auto-loaded into the agent system prompt every session |
| MCP client | ✅ | `~/.anvil/mcp.json`, stdio servers, tools exposed as `mcp_<server>_<tool>`, approval-gated; demo server included |
| Session persistence | ✅ | auto-saved to `~/.anvil/sessions/`, resume from header dropdown |
| Obsidian vault tools | ✅ | vault_search/read/write, auto-detected, settings picker |
| Windowed-app test guard | ✅ | agent shell forces GUI toolkits headless + hard-kills process tree on timeout (games can't hang the agent) |
| Git commit/PR workflows | ✅ | works via bash tool (git); dedicated UI is optional polish |
| Scheduled/background runs | 🗓 | optional — not core to a coding studio |

## Editor (Cursor)
| Feature | Status | Notes |
|---|---|---|
| File explorer pane | ✅ | tree view of workspace |
| Editor tabs + syntax highlighting | ✅ | Python highlighter v1; more languages 🗓 |
| Chat pane with @-file mentions | ✅ | `@path/to/file` injects file content |
| Agent vs Chat modes | ✅ | segmented selector; agent mode now works for Ollama, Anthropic, LM Studio, AND remote OpenAI-compat models (GLM/MiniMax/DeepSeek) via tool-calling loop |
| Diff review before apply | ✅ | red/green DiffCard with Accept/Reject in chat; editor shows reload banner on agent edits |
| Tab autocomplete | ✅ | Tab in editor → FIM completion via qwen2.5-coder; Tab accepts, Esc/typing rejects |
| Editor live-sync | ✅ | open editor shows "changed on disk" banner when the agent edits that file; one-click reload |
| Terminal pane | ✅ | QProcess shell under the editor (Ctrl+` toggle), command history, runs in workspace |
| Semantic codebase indexing | ✅ | nomic-embed index (⌕ Index button), `codebase_search` agent tool finds code by meaning; cache auto-detected per workspace |
| Rules (.cursorrules) | ✅ | same as ANVIL.md |
