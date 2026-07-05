"""Round 11 — the bash tool runs on a real POSIX shell (git-bash) on Windows.

The chess stress run wasted ~6 steps because heredocs and POSIX syntax hit cmd.exe.
Run: py -3.14 -X utf8 tests/test_round11.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import tools  # noqa: E402


def test_posix_shell_used_when_available():
    def body():
        ws = Path(tempfile.mkdtemp())
        bash = tools._posix_shell()
        if not bash:
            # No git-bash on this box — the cmd.exe fallback must still run a basic cmd.
            out = tools._run_bash("echo hello", ws, 30)
            expect("hello" in out, "cmd.exe fallback still runs simple commands")
            return
        # POSIX arithmetic — cmd.exe cannot do $((...))
        out = tools._run_bash("echo $((2 + 3))", ws, 30)
        expect("[exit 0]" in out and "5" in out, f"POSIX arithmetic works: {out!r}")
    check("bash: POSIX shell runs $((...)) (or cmd fallback runs echo)", body)


def test_heredoc_works():
    def body():
        if not tools._posix_shell():
            return  # nothing to prove without a POSIX shell
        ws = Path(tempfile.mkdtemp())
        out = tools._run_bash(
            "python3 - <<'PY'\nprint('heredoc-ok', 6 * 7)\nPY", ws, 30)
        expect("heredoc-ok 42" in out, f"heredoc runs through git-bash: {out!r}")
    check("bash: heredocs run (the exact idiom that broke on cmd.exe)", body)


def test_headless_env_still_forced():
    def body():
        ws = Path(tempfile.mkdtemp())
        # the SDL/Qt headless guard must survive the shell change
        cmd = ("python3 -c \"import os;print('QT='+os.environ.get('QT_QPA_PLATFORM',''))\""
               if tools._posix_shell() else
               "python -c \"import os;print('QT='+os.environ.get('QT_QPA_PLATFORM',''))\"")
        out = tools._run_bash(cmd, ws, 30)
        expect("QT=offscreen" in out, f"headless env is still injected: {out!r}")
    check("bash: headless SDL/Qt env survives the POSIX-shell switch", body)


def test_system32_wsl_launcher_skipped():
    def body():
        # _posix_shell must never return the System32 WSL launcher (it shells into a
        # whole other distro with a different filesystem view of the workspace)
        bash = tools._posix_shell()
        if bash:
            expect("system32" not in bash.lower(), f"not the WSL launcher: {bash}")
    check("bash: never selects the System32 WSL launcher", body)


if __name__ == "__main__":
    print("== posix shell =="); test_posix_shell_used_when_available()
    print("== heredoc =="); test_heredoc_works()
    print("== headless env =="); test_headless_env_still_forced()
    print("== no wsl =="); test_system32_wsl_launcher_skipped()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
