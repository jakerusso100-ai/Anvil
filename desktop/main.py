"""Anvil Desktop v3 — native local AI coding studio (PySide6/Qt).

Cursor/Claude-style: 3-pane layout, Auto model routing via the Copilot,
health monitoring, welcome screen, Enter-to-send, settings dialog.

Run:  py -3.14 anvil/desktop/main.py
"""
from __future__ import annotations

import difflib
import html
import queue
import re
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QStringListModel, Qt, QThread, Signal
from PySide6.QtGui import (QColor, QFont, QKeySequence, QShortcut,
                           QSyntaxHighlighter, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox,
    QFileDialog, QFileSystemModel, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QTabWidget, QTreeView, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
import agent  # noqa: E402
import copilot  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402
import sessions  # noqa: E402

AUTO = "__auto__"

DARK = """
QMainWindow, QWidget { background: #16161a; color: #ececf1; font-size: 14px; }
QComboBox, QSpinBox, QPlainTextEdit, QTreeView, QTabWidget::pane, QLineEdit {
  background: #1f1f26; border: 1px solid #303039; border-radius: 8px; padding: 5px 9px; color: #ececf1; }
QComboBox:hover, QPushButton#ghost:hover { border-color: #4a4a58; }
QComboBox QAbstractItemView { background: #1f1f26; color: #ececf1; selection-background-color: #303039; }
QPushButton { background: #d97757; color: #fff; border: none; border-radius: 9px;
  padding: 9px 18px; font-weight: 600; }
QPushButton:hover { background: #e08663; }
QPushButton#ghost { background: #1f1f26; border: 1px solid #303039; color: #ececf1; font-weight: 500; }
QPushButton#seg { background: #1f1f26; border: 1px solid #303039; color: #9b9ba7;
  border-radius: 0; padding: 7px 16px; font-weight: 600; }
QPushButton#seg:checked { background: #303039; color: #ececf1; }
QPushButton:disabled { background: #2a2a33; color: #6c6c78; }
QCheckBox { color: #9b9ba7; }
QLabel#muted { color: #9b9ba7; font-size: 12px; }
QLabel#brand { font-size: 17px; font-weight: 700; color: #d97757; }
QScrollArea { border: none; }
QTabBar::tab { background: #16161a; color: #9b9ba7; padding: 6px 14px; border: 1px solid #303039;
  border-bottom: none; border-top-left-radius: 7px; border-top-right-radius: 7px; }
QTabBar::tab:selected { background: #1f1f26; color: #ececf1; }
QTreeView { alternate-background-color: #1a1a20; }
QFrame#card { background: #1d1d24; border: 1px solid #2c2c35; border-radius: 12px; }
QFrame#cardUser { background: #26262e; border: 1px solid #34343e; border-radius: 12px; }
QFrame#cardRev { background: #1d1d24; border: 1px solid #1baf7a; border-radius: 12px; }
QFrame#cardTool { background: #191920; border: 1px solid #3c3c49; border-radius: 9px; }
QFrame#cardRoute { background: #201d2b; border: 1px solid #6a5acd; border-radius: 9px; }
QFrame#cardReviewFail { background: #241d10; border: 1px solid #eab308; border-radius: 12px; }
QFrame#cardReviewPass { background: #12231b; border: 1px solid #1baf7a; border-radius: 12px; }
QFrame#welcome { background: #1d1d24; border: 1px solid #2c2c35; border-radius: 14px; }
QPushButton#banner { background: #2a2410; color: #eab308; border: none; border-bottom: 1px solid #eab308;
  border-radius: 0; padding: 6px; font-weight: 600; text-align: left; }
"""

CODE_CSS = ("<style>pre{background:#101014;border:1px solid #2c2c35;border-radius:8px;"
            "padding:11px;font-family:Consolas,monospace;font-size:13px;color:#e6e6ec;}"
            "code{font-family:Consolas,monospace;background:#101014;padding:1px 4px;border-radius:4px;}</style>")

PY_KEYWORDS = ("def class return if elif else for while try except finally with as import "
               "from pass break continue lambda yield raise assert global nonlocal in is "
               "not and or None True False async await match case").split()

SUGGESTIONS = [
    "Make a snake game in pygame in this folder",
    "Explain what this project does (use the file tools)",
    "Find and fix any bug in @",
]


def md_to_html(text: str) -> str:
    out, parts = "", text.split("```")
    for i, part in enumerate(parts):
        if i % 2 == 1:
            body = re.sub(r"^[a-zA-Z0-9]*\n", "", part)
            out += f"<pre>{html.escape(body)}</pre>"
        else:
            seg = html.escape(part).replace("\n", "<br>")
            seg = re.sub(r"`([^`]+)`", r"<code>\1</code>", seg)
            out += seg
    return CODE_CSS + out


class PyHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self.rules = []
        kw = QTextCharFormat(); kw.setForeground(QColor("#d97757"))
        for w in PY_KEYWORDS:
            self.rules.append((re.compile(rf"\b{w}\b"), kw))
        st = QTextCharFormat(); st.setForeground(QColor("#1baf7a"))
        self.rules.append((re.compile(r"(['\"]).*?\1"), st))
        cm = QTextCharFormat(); cm.setForeground(QColor("#6c6c78"))
        self.rules.append((re.compile(r"#[^\n]*"), cm))
        fn = QTextCharFormat(); fn.setForeground(QColor("#eab308"))
        self.rules.append((re.compile(r"\bdef\s+(\w+)"), fn))

    def highlightBlock(self, text):
        for rx, fmt in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class CompletionWorker(QThread):
    ready = Signal(str)

    def __init__(self, prefix: str, suffix: str):
        super().__init__()
        self.prefix, self.suffix = prefix, suffix

    def run(self):
        self.ready.emit(llm.fim_complete(self.prefix, self.suffix))


class CodeEdit(QPlainTextEdit):
    """Editor with Tab-to-complete (Cursor Tab): Tab fetches an FIM suggestion,
    inserts it as selected ghost text; Tab again accepts, Esc/typing rejects."""
    def __init__(self):
        super().__init__()
        self._pending = None       # (start_pos, text) of an inserted suggestion
        self._cw = None

    def keyPressEvent(self, e):
        if self._pending and e.key() == Qt.Key_Tab:
            # accept: move cursor to end of suggestion, clear selection
            start, text = self._pending
            cur = self.textCursor(); cur.clearSelection()
            cur.setPosition(start + len(text)); self.setTextCursor(cur)
            self._pending = None
            return
        if self._pending:
            # any other key rejects the ghost text
            start, text = self._pending
            cur = self.textCursor()
            cur.setPosition(start); cur.setPosition(start + len(text), QTextCursor.KeepAnchor)
            cur.removeSelectedText(); self.setTextCursor(cur)
            self._pending = None
            if e.key() == Qt.Key_Escape:
                return
        if e.key() == Qt.Key_Tab and not (e.modifiers() & Qt.ShiftModifier):
            self._request_completion()
            return
        super().keyPressEvent(e)

    def _request_completion(self):
        if self._cw and self._cw.isRunning():
            return
        cur = self.textCursor()
        pos = cur.position()
        full = self.toPlainText()
        prefix, suffix = full[:pos], full[pos:]
        if not prefix.strip():
            self.insertPlainText("    ")  # empty line -> normal indent
            return
        self._cw = CompletionWorker(prefix[-2000:], suffix[:500])
        self._cw.ready.connect(self._insert_suggestion)
        self._cw.start()

    def _insert_suggestion(self, text: str):
        text = (text or "").split("\n\n")[0].rstrip()  # first block only
        if not text:
            return
        cur = self.textCursor()
        start = cur.position()
        cur.insertText(text)
        # select the inserted text so it reads as a ghost suggestion
        cur.setPosition(start); cur.setPosition(start + len(text), QTextCursor.KeepAnchor)
        self.setTextCursor(cur)
        self._pending = (start, text)


class EditorTab(QWidget):
    """Editor with a banner that appears when the agent edits this file on disk,
    offering one-click reload (Cursor-style live sync), and Tab-to-complete."""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        self.banner = QPushButton("● changed on disk by the agent — click to reload")
        self.banner.setObjectName("banner"); self.banner.clicked.connect(self.reload)
        self.banner.hide(); lay.addWidget(self.banner)
        self.edit = CodeEdit()
        self.edit.setFont(QFont("Consolas", 11))
        self.edit.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
        if path.suffix == ".py":
            self.hl = PyHighlighter(self.edit.document())
        lay.addWidget(self.edit)
        self._on_disk = self.edit.toPlainText()
        self.dirty = False  # agent changed the file on disk since last sync

    def save(self):
        self.path.write_text(self.edit.toPlainText(), encoding="utf-8")
        self._on_disk = self.edit.toPlainText()
        self.dirty = False
        self.banner.hide()

    def reload(self):
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        pos = self.edit.textCursor().position()
        self.edit.setPlainText(text)
        cur = self.edit.textCursor()
        cur.setPosition(min(pos, len(text)))
        self.edit.setTextCursor(cur)
        self._on_disk = text
        self.dirty = False
        self.banner.hide()

    def note_external_change(self):
        """Called when the agent writes this file. Show banner unless unchanged."""
        try:
            disk = self.path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        if disk != self.edit.toPlainText():
            self.dirty = True
            self.banner.show()


class TerminalPane(QWidget):
    """A real workspace shell: type commands, see output. Runs in the current
    workspace via QProcess so long commands don't freeze the UI."""
    def __init__(self, get_workspace):
        super().__init__()
        from PySide6.QtCore import QProcess
        self.get_workspace = get_workspace
        self.proc = None
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 4, 6, 6); lay.setSpacing(4)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        self.out.setFont(QFont("Consolas", 10))
        lay.addWidget(self.out, 1)
        row = QHBoxLayout()
        self.prompt = QLabel("›"); self.prompt.setObjectName("muted"); row.addWidget(self.prompt)
        self.cmd = QPlainTextEdit(); self.cmd.setFixedHeight(30)
        self.cmd.setFont(QFont("Consolas", 10)); row.addWidget(self.cmd, 1)
        self.run_btn = QPushButton("Run"); self.run_btn.setObjectName("ghost")
        self.run_btn.setFixedWidth(60); self.run_btn.clicked.connect(self.run)
        row.addWidget(self.run_btn)
        lay.addLayout(row)
        self._QProcess = QProcess
        self.history: list[str] = []
        self.hist_idx = 0
        self.cmd.installEventFilter(self)

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self.cmd and ev.type() == QEvent.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not (ev.modifiers() & Qt.ShiftModifier):
                self.run()
                return True
            if ev.key() == Qt.Key_Up and self.history:
                self.hist_idx = max(0, self.hist_idx - 1)
                self.cmd.setPlainText(self.history[self.hist_idx])
                return True
            if ev.key() == Qt.Key_Down and self.history:
                self.hist_idx = min(len(self.history), self.hist_idx + 1)
                self.cmd.setPlainText(self.history[self.hist_idx] if self.hist_idx < len(self.history) else "")
                return True
        return super().eventFilter(obj, ev)

    def _append(self, text: str):
        self.out.appendPlainText(text.rstrip("\n"))
        sb = self.out.verticalScrollBar(); sb.setValue(sb.maximum())

    def run(self):
        cmd = self.cmd.toPlainText().strip()
        if not cmd or (self.proc and self.proc.state() != self._QProcess.NotRunning):
            return
        self.history.append(cmd); self.hist_idx = len(self.history)
        self.cmd.clear()
        self._append(f"› {cmd}")
        self.proc = self._QProcess(self)
        self.proc.setWorkingDirectory(self.get_workspace())
        self.proc.setProcessChannelMode(self._QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(
            lambda: self._append(bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")))
        self.proc.finished.connect(lambda code, _: self._append(f"[exit {code}]"))
        self.proc.start("cmd.exe", ["/c", cmd])


class Composer(QPlainTextEdit):
    """Enter sends, Shift+Enter inserts a newline — like Claude and Cursor.
    When the @/command completion popup is open, Enter/Tab accept the completion
    instead of sending."""
    submit = Signal()
    pick_completion = Signal()

    def __init__(self, *a):
        super().__init__(*a)
        self.completer = None  # attached by Main

    def keyPressEvent(self, e):
        popup_open = self.completer is not None and self.completer.popup().isVisible()
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab) and popup_open:
            self.pick_completion.emit()
            return
        if e.key() == Qt.Key_Escape and popup_open:
            self.completer.popup().hide()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
        else:
            super().keyPressEvent(e)


class Bubble(QFrame):
    def __init__(self, title: str, obj_name: str = "card"):
        super().__init__()
        self.setObjectName(obj_name)
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 9, 14, 11)
        self.title = QLabel(title); self.title.setObjectName("muted"); self.title.setTextFormat(Qt.RichText)
        lay.addWidget(self.title)
        self.body = QLabel(); self.body.setTextFormat(Qt.RichText)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.body)
        self._raw = ""

    def append_text(self, chunk: str):
        self._raw += chunk
        # very long streams: keep full text in history but render a bounded view
        if len(self._raw) > 60_000:
            self.body.setText(md_to_html(self._raw[:60_000]) +
                              "<br><i>… long output — view bounded (full text kept)</i>")
        else:
            self.body.setText(md_to_html(self._raw))

    def set_text(self, text: str, rich: bool = False):
        self._raw = text
        self.body.setText(text if rich else md_to_html(text))


class DiffCard(QFrame):
    """Cursor-style red/green diff with Accept / Reject — Reject reverts the file."""

    def __init__(self, path: str, before: str, after: str, workspace: str, run_id: str):
        super().__init__()
        self.setObjectName("cardTool")
        self.path, self.workspace, self.run_id = path, workspace, run_id
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 8, 12, 10)
        top = QHBoxLayout()
        t = QLabel(f"✏ <b>{html.escape(path)}</b>"); t.setTextFormat(Qt.RichText)
        t.setObjectName("muted"); top.addWidget(t); top.addStretch(1)
        self.accept_btn = QPushButton("✓ Accept"); self.accept_btn.setObjectName("ghost")
        self.reject_btn = QPushButton("✗ Reject"); self.reject_btn.setObjectName("ghost")
        self.accept_btn.clicked.connect(self._accept)
        self.reject_btn.clicked.connect(self._reject)
        top.addWidget(self.accept_btn); top.addWidget(self.reject_btn)
        lay.addLayout(top)
        body = QLabel(); body.setTextFormat(Qt.RichText); body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setText(self._render(before, after))
        lay.addWidget(body)
        self.state = QLabel(""); self.state.setObjectName("muted"); lay.addWidget(self.state)

    def _render(self, before: str, after: str) -> str:
        lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm=""))[2:]
        if len(lines) > 120:
            lines = lines[:120] + [f"… {len(lines) - 120} more lines"]
        out = []
        for ln in lines:
            e = html.escape(ln) or "&nbsp;"
            if ln.startswith("+"):
                out.append(f"<span style='color:#7ee2a8;background:#12231b;'>{e}</span>")
            elif ln.startswith("-"):
                out.append(f"<span style='color:#f09595;background:#2a1515;'>{e}</span>")
            elif ln.startswith("@@"):
                out.append(f"<span style='color:#9b9ba7;'>{e}</span>")
            else:
                out.append(e)
        return ("<div style='font-family:Consolas,monospace;font-size:12px;"
                "white-space:pre-wrap;'>" + "<br>".join(out) + "</div>")

    def _done(self, msg: str):
        self.accept_btn.setEnabled(False); self.reject_btn.setEnabled(False)
        self.state.setText(msg)

    def _accept(self):
        self._done("accepted")

    def _reject(self):
        ok = agent.restore_file(self.workspace, self.run_id, self.path)
        self._done("rejected — file reverted" if ok else "revert failed (file missing?)")


class Worker(QThread):
    """Routing + generation off the UI thread, with copilot fallback redirect,
    Claude Code-style permission modes, and cooperative stop."""
    event = Signal(dict)
    ask = Signal(str, str, str)  # tool name, args preview, diff detail

    def __init__(self, mode: str, kwargs: dict, perm_mode: str,
                 router_model: str, allow_api: bool, user_text: str, workspace: str):
        super().__init__()
        self.mode, self.kwargs, self.perm = mode, kwargs, perm_mode
        self.router_model, self.allow_api, self.user_text = router_model, allow_api, user_text
        self.workspace = workspace
        self.reply: queue.Queue = queue.Queue()
        self.stopping = False

    def _diff_preview(self, name: str, args: dict) -> str:
        """Unified diff of what a write/edit WOULD do — shown in the Ask dialog."""
        try:
            path = args.get("path", "")
            p = Path(self.workspace) / path
            before = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            if name == "write_file":
                after = args.get("content", "")
            elif name == "edit_file":
                after = before.replace(args.get("old_text", ""), args.get("new_text", ""), 1)
            else:
                return ""
            return "\n".join(difflib.unified_diff(
                before.splitlines(), after.splitlines(),
                fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))[:8000]
        except Exception:
            return ""

    def approve(self, name: str, args: dict) -> bool:
        if self.stopping:
            return False
        if self.perm == "Bypass":
            return True
        if self.perm == "Plan":
            return False  # read-only exploration; edits/commands blocked
        if self.perm == "Accept edits" and name in ("write_file", "edit_file"):
            return True
        detail = self._diff_preview(name, args) if name in ("write_file", "edit_file") else ""
        self.ask.emit(name, str(args)[:600], detail)
        return bool(self.reply.get())

    def _make_gen(self):
        if self.mode == "prompt":
            return agent.run_prompt_maker(approve=self.approve, **self.kwargs)
        if self.mode == "agent":
            if "review" in self.kwargs:  # build + gated frontier review of the result
                return agent.run_agent_reviewed(approve=self.approve, **self.kwargs)
            return agent.run_agent(approve=self.approve, **self.kwargs)
        return pipeline.run_turn(**self.kwargs)

    def run(self):
        try:
            if self.kwargs["model"] == AUTO:
                self.event.emit({"type": "stage", "stage": "copilot routing", "model": self.router_model})
                r = copilot.route(self.user_text, self.router_model, self.allow_api)
                self.kwargs["model"] = r["model"]
                self.event.emit({"type": "routed", **r})
            tried = set()
            while True:
                tried.add(self.kwargs["model"])
                try:
                    for ev in self._make_gen():
                        if self.stopping:
                            self.event.emit({"type": "review_error", "error": "stopped by user"})
                            self.event.emit({"type": "final", "cost": 0, "reviewed": False,
                                             "revised": False, "passed": None, "answer": ""})
                            return
                        self.event.emit(ev)
                    return
                except Exception as e:
                    if self.stopping:
                        raise
                    fb = copilot.fallback_for(self.kwargs["model"], self.allow_api)
                    if not fb or fb in tried:
                        raise
                    self.event.emit({"type": "redirect", "from": self.kwargs["model"],
                                     "to": fb, "error": f"{type(e).__name__}: {e}"})
                    self.kwargs["model"] = fb
        except Exception as e:
            self.event.emit({"type": "review_error", "error": f"{type(e).__name__}: {e}"})
            self.event.emit({"type": "final", "cost": 0, "reviewed": False,
                             "revised": False, "passed": None, "answer": ""})


class HealthWorker(QThread):
    done = Signal(list)

    def run(self):
        self.done.emit(copilot.health())


class IndexWorker(QThread):
    progress = Signal(int, int)
    done = Signal(dict)

    def __init__(self, workspace: str, vault: str | None):
        super().__init__()
        self.workspace, self.vault = workspace, vault

    def run(self):
        import semindex
        try:
            stats = semindex.build_index(
                self.workspace, extra_roots=[self.vault] if self.vault else None,
                progress=lambda i, n: self.progress.emit(i, n))
        except Exception as e:
            stats = {"error": f"{type(e).__name__}: {e}"}
        self.done.emit(stats)


class SettingsDialog(QDialog):
    def __init__(self, parent, s: dict):
        super().__init__(parent)
        self.setWindowTitle("Anvil settings")
        form = QFormLayout(self)
        self.reviewer = QComboBox(); self.reviewer.addItems(llm.API_MODELS)
        self.reviewer.setCurrentText(s["reviewer"]); form.addRow("Reviewer model", self.reviewer)
        self.review = QCheckBox(); self.review.setChecked(s["review"]); form.addRow("Review code (Chat mode)", self.review)
        self.review_agent = QCheckBox(); self.review_agent.setChecked(s["review_agent"])
        form.addRow("Review builds (Agent mode)", self.review_agent)
        self.autofix = QCheckBox(); self.autofix.setChecked(s["auto_fix"]); form.addRow("Auto-fix on issues", self.autofix)
        self.rounds = QSpinBox(); self.rounds.setRange(1, 5); self.rounds.setValue(s["rounds"])
        form.addRow("Max fix rounds", self.rounds)
        self.approve = QCheckBox(); self.approve.setChecked(s["auto_approve"])
        form.addRow("Auto-approve agent tools", self.approve)
        self.router = QComboBox(); self.router.addItems(llm.list_local_models() or [copilot.DEFAULT_ROUTER])
        self.router.setCurrentText(s["router"]); form.addRow("Copilot router model", self.router)
        self.allow_api = QCheckBox(); self.allow_api.setChecked(s["allow_api"])
        form.addRow("Copilot may pick paid API models", self.allow_api)
        import tools as _tools
        self.vault = QComboBox(); self.vault.setEditable(True)
        self.vault.addItem("")  # none
        for v in _tools.detect_vaults():
            self.vault.addItem(v)
        self.vault.setCurrentText(s.get("vault", ""))
        form.addRow("Obsidian vault (notes as AI context)", self.vault)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        return {"reviewer": self.reviewer.currentText(), "review": self.review.isChecked(),
                "review_agent": self.review_agent.isChecked(),
                "auto_fix": self.autofix.isChecked(), "rounds": self.rounds.value(),
                "auto_approve": self.approve.isChecked(), "router": self.router.currentText(),
                "allow_api": self.allow_api.isChecked(), "vault": self.vault.currentText().strip()}


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anvil — local AI coding studio")
        self.resize(1500, 920)
        self.history: list[dict] = []
        self.session_cost = 0.0
        self.last_model: str | None = None
        self.last_run_id: str | None = None
        self.worker: Worker | None = None
        self.workspace = str(Path.home())
        import tools as _tools
        vaults = _tools.detect_vaults()
        self.settings = {"reviewer": "claude-haiku-4-5", "review": True,
                         "review_agent": True, "auto_fix": True,
                         "rounds": 2, "auto_approve": False,
                         "router": copilot.DEFAULT_ROUTER, "allow_api": True,
                         "vault": vaults[0] if vaults else ""}
        _tools.VAULT_PATH = self.settings["vault"] or None

        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0)

        # ================= header =================
        head = QWidget(); hl = QHBoxLayout(head); hl.setContentsMargins(14, 9, 14, 9)
        brand = QLabel("⚒ Anvil"); brand.setObjectName("brand"); hl.addWidget(brand)
        self.new_btn = QPushButton("+ New chat"); self.new_btn.setObjectName("ghost")
        self.new_btn.clicked.connect(self.new_chat); hl.addWidget(self.new_btn)
        self.sess_combo = QComboBox(); self.sess_combo.setMinimumWidth(190)
        self.sess_combo.setToolTip("Previous sessions — pick one to resume it")
        self.sess_combo.activated.connect(self.load_session)
        hl.addWidget(self.sess_combo)
        self.open_btn = QPushButton("Open folder"); self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(self.pick_folder); hl.addWidget(self.open_btn)

        seg = QWidget(); sl = QHBoxLayout(seg); sl.setContentsMargins(8, 0, 8, 0); sl.setSpacing(0)
        self.btn_agent = QPushButton("Agent"); self.btn_agent.setObjectName("seg")
        self.btn_chat = QPushButton("Chat"); self.btn_chat.setObjectName("seg")
        self.btn_prompt = QPushButton("Prompt"); self.btn_prompt.setObjectName("seg")
        self.btn_prompt.setToolTip("Prompt Maker: the model interviews you (2D or 3D? "
                                   "solo or multiplayer? …) and writes a polished build "
                                   "prompt you can hand to the builder.")
        for b in (self.btn_agent, self.btn_chat, self.btn_prompt):
            b.setCheckable(True); sl.addWidget(b)
        self.btn_agent.setChecked(True)
        self.btn_agent.clicked.connect(lambda: self.set_mode("Agent"))
        self.btn_chat.clicked.connect(lambda: self.set_mode("Chat"))
        self.btn_prompt.clicked.connect(lambda: self.set_mode("Prompt"))
        hl.addWidget(seg)

        self.coder = QComboBox(); self.coder.setMinimumWidth(250); hl.addWidget(self.coder)
        self.settings_btn = QPushButton("⚙"); self.settings_btn.setObjectName("ghost")
        self.settings_btn.setFixedWidth(40); self.settings_btn.clicked.connect(self.open_settings)
        hl.addWidget(self.settings_btn)
        self.restore_btn = QPushButton("↩ Checkpoint"); self.restore_btn.setObjectName("ghost")
        self.restore_btn.clicked.connect(self.restore_checkpoint); self.restore_btn.setEnabled(False)
        hl.addWidget(self.restore_btn)
        self.index_btn = QPushButton("⌕ Index"); self.index_btn.setObjectName("ghost")
        self.index_btn.setToolTip("Build a semantic index of this workspace so the agent can "
                                  "search your codebase by meaning")
        self.index_btn.clicked.connect(self.build_index); hl.addWidget(self.index_btn)
        hl.addStretch(1)
        self.health_lbl = QLabel("● ● ●"); self.health_lbl.setObjectName("muted")
        self.health_lbl.setToolTip("checking system health…"); hl.addWidget(self.health_lbl)
        self.cost_lbl = QLabel("$0.00000"); self.cost_lbl.setObjectName("muted"); hl.addWidget(self.cost_lbl)
        outer.addWidget(head)

        # ================= panes =================
        split = QSplitter(Qt.Horizontal)
        self.fs = QFileSystemModel(); self.fs.setRootPath(self.workspace)
        self.fs.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.tree = QTreeView(); self.tree.setModel(self.fs)
        self.tree.setRootIndex(self.fs.index(self.workspace))
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.doubleClicked.connect(self.open_from_tree)
        split.addWidget(self.tree)

        center = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.tabs.removeTab)
        ph = QLabel("Double-click a file to open\nCtrl+S saves · Ctrl+` toggles terminal")
        ph.setAlignment(Qt.AlignCenter); ph.setObjectName("muted")
        self.tabs.addTab(ph, "welcome")
        center.addWidget(self.tabs)
        self.terminal = TerminalPane(lambda: self.workspace)
        center.addWidget(self.terminal)
        center.setSizes([600, 200])
        self.center_split = center
        split.addWidget(center)

        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(6, 0, 6, 0)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        inner = QWidget(); self.chat = QVBoxLayout(inner)
        self.chat.setContentsMargins(10, 10, 10, 10); self.chat.setSpacing(9)
        self.chat.addStretch(1)
        self.scroll.setWidget(inner)
        rl.addWidget(self.scroll, 1)
        self.status = QLabel(""); self.status.setObjectName("muted"); rl.addWidget(self.status)
        comp = QWidget(); cv = QVBoxLayout(comp); cv.setContentsMargins(0, 4, 0, 8); cv.setSpacing(4)
        row = QHBoxLayout()
        self.input = Composer()
        self.input.setPlaceholderText("Ask anything… @file for context, / for commands. Enter sends, Shift+Enter = newline")
        self.input.setFixedHeight(80); self.input.submit.connect(self.send_or_stop)
        row.addWidget(self.input, 1)
        self.send_btn = QPushButton("➤"); self.send_btn.setFixedWidth(54)
        self.send_btn.clicked.connect(self.send_or_stop); row.addWidget(self.send_btn)
        cv.addLayout(row)
        under = QHBoxLayout()
        under.addWidget(QLabel("permissions:"))
        self.perm = QComboBox(); self.perm.addItems(["Ask", "Accept edits", "Plan", "Bypass"])
        self.perm.setCurrentText("Accept edits")
        self.perm.setToolTip("Ask: approve every edit/command (with diff preview)\n"
                             "Accept edits: file edits auto, commands ask\n"
                             "Plan: read-only exploration, no changes\n"
                             "Bypass: everything runs without asking")
        under.addWidget(self.perm)
        under.addStretch(1)
        self.ctx_lbl = QLabel("context ≈ 0 tok"); self.ctx_lbl.setObjectName("muted")
        under.addWidget(self.ctx_lbl)
        cv.addLayout(under)
        rl.addWidget(comp)

        # @file and /command autocomplete
        self.ws_files: list[str] = []
        self.completer = QCompleter(self)
        self.completer.setWidget(self.input)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)
        self.input.completer = self.completer
        self.input.pick_completion.connect(self.accept_current_completion)
        self.input.textChanged.connect(self.maybe_complete)
        split.addWidget(right)
        split.setSizes([230, 610, 660])
        outer.addWidget(split, 1)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_tab)
        QShortcut(QKeySequence("Ctrl+`"), self, activated=self.toggle_terminal)
        self.mode = "Agent"
        self.session_id = sessions.new_id()
        self.load_models()
        self.refresh_sessions()
        self._refresh_index_state()
        self.show_welcome()
        self.hw = HealthWorker(); self.hw.done.connect(self.on_health); self.hw.start()

    # ================= sessions =================
    def refresh_sessions(self):
        self.sess_combo.blockSignals(True)
        self.sess_combo.clear()
        self.sess_combo.addItem("↺ sessions…", None)
        for s in sessions.list_sessions():
            self.sess_combo.addItem(f"{s['title'][:34]}  · {s['updated']}", s["id"])
        self.sess_combo.setCurrentIndex(0)
        self.sess_combo.blockSignals(False)

    def _reset_chat_ui(self):
        while self.chat.count() > 1:
            item = self.chat.itemAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            self.chat.removeItem(item)

    def new_chat(self):
        if self.worker and self.worker.isRunning():
            self.status.setText("can't start a new chat while a turn is running")
            return
        if self.history:
            sessions.save(self.session_id, self.history, self.workspace, self.session_cost)
        self.history = []
        self.session_id = sessions.new_id()
        self._reset_chat_ui()
        self.update_ctx_meter()
        self.refresh_sessions()
        self.show_welcome()

    def load_session(self, index: int):
        sid = self.sess_combo.itemData(index)
        if not sid:
            return
        if self.worker and self.worker.isRunning():
            self.status.setText("can't switch sessions while a turn is running")
            return
        data = sessions.load(sid)
        if not data:
            self.status.setText("session file missing")
            return
        if self.history:
            sessions.save(self.session_id, self.history, self.workspace, self.session_cost)
        self.session_id = data["id"]
        self.history = data.get("history", [])
        ws = data.get("workspace")
        if ws and Path(ws).is_dir():
            self.workspace = ws
            self.tree.setRootIndex(self.fs.index(ws))
            self.setWindowTitle(f"Anvil — {ws}")
            self.index_workspace()
            self._refresh_index_state()
        self._reset_chat_ui()
        for m in self.history:
            if m["role"] == "user":
                self.add_bubble("you", "cardUser").set_text(str(m["content"])[:4000])
            elif m["role"] == "assistant":
                self.add_bubble("assistant").set_text(str(m["content"])[:8000])
        self.update_ctx_meter()
        self.status.setText(f"resumed session · {len(self.history)} messages")

    # ================= welcome / health =================
    def show_welcome(self):
        card = Bubble("welcome to Anvil", "welcome")
        card.set_text(
            "Your local AI coding studio. <b>Auto</b> mode lets the copilot pick the right "
            "model per request — local for most things, paid only when it's worth it.<br><br>"
            "Try one of these:", rich=True)
        self.chat.insertWidget(self.chat.count() - 1, card)
        row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(4, 0, 4, 0)
        for s in SUGGESTIONS:
            b = QPushButton(s[:44] + ("…" if len(s) > 44 else "")); b.setObjectName("ghost")
            b.clicked.connect(lambda _, t=s: self.input.setPlainText(t))
            rl.addWidget(b)
        self.chat.insertWidget(self.chat.count() - 1, row)

    def on_health(self, items: list):
        dots, tips = [], []
        for it in items:
            dots.append(f"<span style='color:{'#1baf7a' if it['ok'] else '#ef4444'}'>●</span>")
            tips.append(f"{'✓' if it['ok'] else '✗'} {it['name']}: {it['detail']}")
        self.health_lbl.setText(" ".join(dots))
        self.health_lbl.setToolTip("\n".join(tips))

    # ================= workspace / editor =================
    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Open workspace folder", self.workspace)
        if d:
            self.workspace = d
            self.tree.setRootIndex(self.fs.index(d))
            self.setWindowTitle(f"Anvil — {d}")
            self.add_bubble("workspace", "card").set_text(f"Workspace: {d}")
            self.index_workspace()
            self._refresh_index_state()

    def index_workspace(self):
        skip = {".git", "node_modules", "__pycache__", ".anvil", ".venv", "dist", "build"}
        files = []
        root = Path(self.workspace)
        try:
            for p in root.rglob("*"):
                if len(files) >= 800:
                    break
                if p.is_file() and not (set(p.relative_to(root).parts[:-1]) & skip):
                    files.append(str(p.relative_to(root)).replace("\\", "/"))
        except Exception:
            pass
        self.ws_files = files

    def _current_token(self) -> tuple[str, int]:
        tc = self.input.textCursor()
        text = self.input.toPlainText()[:tc.position()]
        m = re.search(r"(\S+)$", text)
        return (m.group(1), m.start(1)) if m else ("", tc.position())

    def maybe_complete(self):
        token, _ = self._current_token()
        if token.startswith("@") and len(token) > 1:
            hits = [f"@{f}" for f in self.ws_files if token[1:].lower() in f.lower()][:12]
        elif token.startswith("/") and self.input.toPlainText().strip() == token:
            cmds = ["/clear", "/model ", "/health", "/help"]
            hits = [c for c in cmds if c.startswith(token)]
        else:
            self.completer.popup().hide()
            return
        if not hits:
            self.completer.popup().hide()
            return
        self.completer.setModel(QStringListModel(hits))
        self.completer.setCompletionPrefix("")
        cr = self.input.cursorRect()
        cr.setWidth(420)
        self.completer.complete(cr)

    def accept_current_completion(self):
        popup = self.completer.popup()
        idx = popup.currentIndex()
        model = self.completer.model()
        text = (model.data(idx) if idx.isValid()
                else model.data(model.index(0, 0)) if model.rowCount() else None)
        if text:
            self.insert_completion(text)

    def insert_completion(self, completion: str):
        token, start = self._current_token()
        tc = self.input.textCursor()
        tc.setPosition(start, QTextCursor.MoveAnchor)
        tc.setPosition(start + len(token), QTextCursor.KeepAnchor)
        tc.insertText(completion + " ")
        self.completer.popup().hide()

    def open_from_tree(self, idx):
        p = Path(self.fs.filePath(idx))
        if p.is_file():
            try:
                ed = EditorTab(p)
            except Exception as e:
                QMessageBox.warning(self, "open failed", str(e)); return
            self.tabs.addTab(ed, p.name)
            self.tabs.setCurrentWidget(ed)

    def save_tab(self):
        w = self.tabs.currentWidget()
        if isinstance(w, EditorTab):
            w.save(); self.status.setText(f"saved {w.path.name}")

    def toggle_terminal(self):
        vis = self.terminal.isVisible()
        self.terminal.setVisible(not vis)
        if not vis:
            self.center_split.setSizes([600, 220])
            self.terminal.cmd.setFocus()

    def notify_editors_of_edit(self, rel_path: str):
        """When the agent writes a file, flag any open editor for that file."""
        target = (Path(self.workspace) / rel_path).resolve()
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, EditorTab) and w.path.resolve() == target:
                w.note_external_change()

    def set_mode(self, mode: str):
        self.mode = mode
        self.btn_agent.setChecked(mode == "Agent")
        self.btn_chat.setChecked(mode == "Chat")
        self.btn_prompt.setChecked(mode == "Prompt")

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings)
        if dlg.exec():
            self.settings.update(dlg.values())
            import tools as _tools
            _tools.VAULT_PATH = self.settings.get("vault") or None

    # ================= models =================
    def load_models(self):
        self.coder.addItem("✨ Auto — copilot picks", AUTO)
        local = llm.list_local_models()
        roster_local = [m for m in copilot.ROSTER.values() if m in local]
        for m in roster_local:
            self.coder.addItem(f"★ {m}", m)
        for m in local:
            if m not in roster_local:
                self.coder.addItem(m, m)
        for m in llm.API_MODELS:
            self.coder.addItem(f"{m}  (API)", m)
        for rm in llm.list_remote_models():
            suffix = "" if rm["has_key"] else "  — needs key"
            self.coder.addItem(f"{rm['label']}  ({rm['provider']}){suffix}", rm["spec"])
        self.coder.setCurrentIndex(0)

    # ================= chat =================
    def add_bubble(self, title: str, obj: str = "card") -> Bubble:
        b = Bubble(title, obj)
        self.chat.insertWidget(self.chat.count() - 1, b)
        QApplication.processEvents()
        sb = self.scroll.verticalScrollBar(); sb.setValue(sb.maximum())
        return b

    def expand_mentions(self, text: str) -> str:
        def repl(m):
            rel = m.group(1)
            p = Path(self.workspace) / rel
            if p.is_file():
                body = p.read_text(encoding="utf-8", errors="replace")[:30000]
                return f"\n\n<file path=\"{rel}\">\n{body}\n</file>\n"
            return m.group(0)
        return re.sub(r"@([\w./\\-]+)", repl, text)

    def slash(self, text: str) -> bool:
        if not text.startswith("/"):
            return False
        cmd, _, arg = text.partition(" ")
        if cmd == "/clear":
            if self.worker and self.worker.isRunning():
                self.status.setText("can't clear while a turn is running — stop it first")
                return True
            self.history.clear()
            while self.chat.count() > 1:
                w = self.chat.itemAt(0).widget()
                if w: w.deleteLater()
                self.chat.removeItem(self.chat.itemAt(0))
            self.status.setText("history cleared")
        elif cmd == "/model" and arg:
            i = self.coder.findData(arg.strip())
            if i >= 0: self.coder.setCurrentIndex(i)
            self.status.setText(f"coder = {self.coder.currentData()}")
        elif cmd == "/health":
            self.hw = HealthWorker(); self.hw.done.connect(self.show_health_card); self.hw.start()
        elif cmd == "/help":
            self.add_bubble("help").set_text(
                "/clear — reset conversation\n/model <name> — switch coder\n/health — system check\n"
                "@path/file — inject a workspace file\n"
                "Auto model: the copilot routes each request to the best model.\n"
                "Agent mode: tools (files, bash, web) + paid review of the build. "
                "Chat mode: coder + reviewer + auto-fix.")
        else:
            self.status.setText(f"unknown command {cmd}")
        return True

    def show_health_card(self, items):
        self.on_health(items)
        card = self.add_bubble("system health")
        card.set_text("<br>".join(
            f"{'🟢' if it['ok'] else '🔴'} <b>{it['name']}</b> — {html.escape(it['detail'])}" for it in items), rich=True)

    def update_ctx_meter(self):
        toks = sum(len(m["content"]) for m in self.history if isinstance(m.get("content"), str)) // 4
        self.ctx_lbl.setText(f"context ≈ {toks:,} tok")

    def send_or_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stopping = True
            self.status.setText("stopping…")
            return
        self.send()

    def send(self):
        text = self.input.toPlainText().strip()
        if not text or (self.worker and self.worker.isRunning()):
            return
        self.input.clear()
        if self.slash(text):
            return
        self.send_btn.setText("⏹")

        model = self.coder.currentData()
        if self.last_model and self.last_model != model and self.last_model != AUTO \
                and not llm.is_api_model(self.last_model) and not self.last_model.startswith("lms/"):
            llm.unload_ollama(self.last_model)
        self.last_model = model

        self.add_bubble("you", "cardUser").set_text(text)
        expanded = self.expand_mentions(text)
        self.history.append({"role": "user", "content": expanded})
        self.update_ctx_meter()
        self.bubbles = {}

        s = self.settings
        perm = self.perm.currentText()
        if self.mode == "Prompt":
            kwargs = {"model": model, "messages": list(self.history), "workspace": self.workspace}
            self.worker = Worker("prompt", kwargs, perm, s["router"], s["allow_api"],
                                 expanded, self.workspace)
        elif self.mode == "Agent":
            kwargs = {"model": model, "messages": list(self.history), "workspace": self.workspace}
            if s["review_agent"]:  # local model builds, then a paid reviewer checks it
                kwargs.update(review=True, reviewer=s["reviewer"],
                              auto_revise=s["auto_fix"], max_rounds=s["rounds"])
            self.worker = Worker("agent", kwargs, perm, s["router"], s["allow_api"],
                                 expanded, self.workspace)
        else:
            kwargs = {"model": model, "messages": list(self.history), "review": s["review"],
                      "reviewer": s["reviewer"], "auto_revise": s["auto_fix"], "max_rounds": s["rounds"]}
            self.worker = Worker("chat", kwargs, "Bypass", s["router"], s["allow_api"],
                                 expanded, self.workspace)
        self.worker.event.connect(self.on_event)
        self.worker.ask.connect(self.on_ask)
        self.worker.start()

    def on_ask(self, name: str, args: str, detail: str):
        box = QMessageBox(self)
        box.setWindowTitle(f"Allow {name}?")
        box.setText(f"The agent wants to run:\n\n{name}({args})")
        if detail:
            box.setInformativeText("Diff preview available below.")
            box.setDetailedText(detail)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        self.worker.reply.put(box.exec() == QMessageBox.Yes)

    # ================= events =================
    def on_event(self, ev: dict):
        t = ev["type"]
        if t == "run_started":
            self.last_run_id = ev["run_id"]
        elif t == "routed":
            why = f" — {ev['why']}" if ev.get("why") else ""
            self.add_bubble("🧭 copilot", "cardRoute").set_text(
                f"<b>{ev['model']}</b> · {ev['category']}{html.escape(why)}", rich=True)
        elif t == "redirect":
            self.add_bubble("🧭 copilot redirect", "cardRoute").set_text(
                f"{ev['from']} failed ({html.escape(ev['error'][:120])}) → retrying with <b>{ev['to']}</b>", rich=True)
        elif t == "stage":
            step = f" step {ev['step']}" if ev.get("step") else (f" round {ev['round']}" if ev.get("round") else "")
            self.status.setText(f"● {ev['stage']}{step} — {ev['model']}")
            if ev["stage"] in ("coding", "thinking"):
                self.active_model = ev["model"]
            if ev["stage"] == "coding":
                self.bubbles[("coder", 0)] = self.add_bubble(f"coder · {ev['model']}")
            elif ev["stage"] == "revising":
                self.bubbles[("revision", ev["round"])] = self.add_bubble(
                    f"auto-fix round {ev['round']} · {ev['model']}", "cardRev")
        elif t == "delta":
            key = (ev["channel"], ev.get("round", 0))
            if key not in self.bubbles:
                who = "agent" if ev["channel"] == "agent" else "coder"
                model = getattr(self, "active_model", None) or ""
                self.bubbles[key] = self.add_bubble(f"{who}{' · ' + model if model else ''}")
            self.bubbles[key].append_text(ev["text"])
            sb = self.scroll.verticalScrollBar(); sb.setValue(sb.maximum())
        elif t == "tool_call":
            args = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in (ev["args"] or {}).items())
            self._tool_card = self.add_bubble(f"🔧 {ev['name']}({args})", "cardTool")
        elif t == "tool_result":
            out = ev["output"]
            if ev.get("denied"):
                self._tool_card.set_text("⛔ denied" + (" (Plan mode is read-only)"
                                         if self.perm.currentText() == "Plan" else " by user"))
            elif len(out) > 500:
                card = self._tool_card
                card.set_text(out[:500] + "\n…")
                more = QPushButton("▸ show all"); more.setObjectName("ghost")
                more.setFixedWidth(110)
                full = out
                more.clicked.connect(lambda _, c=card, f=full, b=more:
                                     (c.set_text(f), b.hide()))
                card.layout().addWidget(more)
            else:
                self._tool_card.set_text(out)
            if ev.get("diff"):
                d = ev["diff"]
                dc = DiffCard(d["path"], d["before"], d["after"], self.workspace, ev["run_id"])
                self.chat.insertWidget(self.chat.count() - 1, dc)
                sb = self.scroll.verticalScrollBar(); sb.setValue(sb.maximum())
                self.notify_editors_of_edit(d["path"])
        elif t == "review":
            ok = ev["verdict"] == "pass"
            card = self.add_bubble(
                f"{'✓ review passed' if ok else '⚠ issues found'} · round {ev['round']} · "
                f"{ev['reviewer']} · ${ev['cost']}",
                "cardReviewPass" if ok else "cardReviewFail")
            lines = [html.escape(ev["summary"])]
            for i in ev["issues"]:
                lines.append(f"<b>{i['severity'].upper()}</b> — {html.escape(i['problem'])}"
                             f"<br><i>fix: {html.escape(i['fix'])}</i>")
            card.set_text("<br><br>".join(lines), rich=True)
        elif t == "review_error":
            self.add_bubble("error", "cardReviewFail").set_text(ev["error"])
        elif t == "final_text":
            if ev.get("answer"):
                self.history.append({"role": "assistant", "content": ev["answer"]})
                if self.mode == "Prompt":
                    bp = agent.extract_build_prompt(ev["answer"])
                    if bp:
                        self.offer_build_prompt(bp)
        elif t == "final":
            self.status.setText("")
            if ev.get("answer"):
                self.history.append({"role": "assistant", "content": ev["answer"]})
            self.session_cost += ev.get("cost", 0) or 0
            self.cost_lbl.setText(f"${self.session_cost:.5f}")
            self.restore_btn.setEnabled(bool(self.last_run_id))
            self.update_ctx_meter()
            sessions.save(self.session_id, self.history, self.workspace, self.session_cost)
            if ev.get("reviewed") and ev.get("revised") and not ev.get("passed"):
                self.add_bubble("note", "cardReviewFail").set_text(
                    "Still had issues after auto-fix rounds — try a stronger coder or reviewer.")
            self.send_btn.setText("➤")
            self.send_btn.setEnabled(True)

    def offer_build_prompt(self, prompt_text: str):
        """Prompt Maker finished a build prompt — show a one-click handoff to the builder."""
        card = self.add_bubble("✓ build prompt ready", "cardReviewPass")
        card.set_text("Prompt Maker drafted a build prompt. Send it to the builder, or "
                      "keep chatting here to refine it first.")
        btn = QPushButton("Send to builder →"); btn.setObjectName("ghost")
        btn.setFixedWidth(170)
        btn.clicked.connect(lambda: self._use_build_prompt(prompt_text))
        card.layout().addWidget(btn)

    def _use_build_prompt(self, prompt_text: str):
        self.set_mode("Agent")
        self.input.setPlainText(prompt_text)
        self.input.setFocus()
        self.status.setText("Switched to Agent mode — review the prompt and hit send to build.")

    def restore_checkpoint(self):
        if not self.last_run_id:
            return
        files = agent.restore_checkpoint(self.workspace, self.last_run_id)
        QMessageBox.information(self, "Checkpoint restored",
                                "Restored:\n" + ("\n".join(files) if files else "(nothing to restore)"))

    def build_index(self):
        if getattr(self, "_idx_worker", None) and self._idx_worker.isRunning():
            return
        self.index_btn.setEnabled(False)
        self.status.setText("● building semantic index…")
        vault = self.settings.get("vault") or None
        self._idx_worker = IndexWorker(self.workspace, vault)
        self._idx_worker.progress.connect(
            lambda i, n: self.status.setText(f"● indexing {i}/{n} chunks…"))
        self._idx_worker.done.connect(self._index_done)
        self._idx_worker.start()

    def _index_done(self, stats: dict):
        self.index_btn.setEnabled(True)
        if stats.get("error"):
            self.status.setText(f"index failed: {stats['error']}")
            return
        import tools as _tools
        _tools.INDEX_READY = True
        self.index_btn.setText(f"⌕ {stats['chunks']} indexed")
        self.status.setText(f"semantic index ready · {stats['chunks']} chunks — "
                            "the agent can now search your codebase by meaning")

    def _refresh_index_state(self):
        """On workspace open/resume, enable codebase_search if a cached index exists."""
        try:
            import semindex
            import tools as _tools
            st = semindex.status(self.workspace)
            _tools.INDEX_READY = st.get("indexed", False)
            if st.get("indexed"):
                self.index_btn.setText(f"⌕ {st['chunks']} indexed")
            else:
                self.index_btn.setText("⌕ Index")
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK)
    app.setFont(QFont("Segoe UI", 10))
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
