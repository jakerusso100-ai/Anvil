"""Round 10 — VRAM-fit routing guardrail (copilot.fit_to_vram).

A model bigger than VRAM spills to CPU and can time out. After routing, the picked
local model must be swapped down to the best-quality installed model that fits.
Run: py -3.14 -X utf8 tests/test_round10.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import copilot  # noqa: E402

GB = 2 ** 30
# realistic installed set on a 16GB card
SIZES = {
    "qwen3-coder-next:latest": 52 * GB,
    "qwen3-coder:30b": 18 * GB,
    "gpt-oss:20b": 13 * GB,
    "granite4:latest": 3 * GB,
}


def _with_env(vram_bytes, sizes, fn):
    real_sizes = copilot._local_model_sizes
    saved = copilot._VRAM.get("b", "unset")
    copilot._local_model_sizes = lambda: sizes
    copilot._VRAM["b"] = vram_bytes
    try:
        return fn()
    finally:
        copilot._local_model_sizes = real_sizes
        if saved == "unset":
            copilot._VRAM.pop("b", None)
        else:
            copilot._VRAM["b"] = saved


def test_swaps_oversized_model():
    def body():
        model, note = _with_env(16 * GB, SIZES,
                                lambda: copilot.fit_to_vram("qwen3-coder-next:latest"))
        expect(model == "gpt-oss:20b", f"52GB model on 16GB card -> gpt-oss:20b, got {model}")
        expect(note and "won't fit" in note, "explains the swap")
    check("vram-fit: oversized build model swaps down to a fitting one", body)


def test_keeps_fitting_model():
    def body():
        model, note = _with_env(16 * GB, SIZES, lambda: copilot.fit_to_vram("gpt-oss:20b"))
        expect(model == "gpt-oss:20b", "a model that fits is left alone")
        expect(note is None, "no note when nothing changed")
    check("vram-fit: a fitting model is untouched", body)


def test_big_card_keeps_big_model():
    def body():
        # on a 48GB card the 52GB model still won't fit at 0.9 headroom, but a 40GB one would
        model, _ = _with_env(80 * GB, SIZES,
                             lambda: copilot.fit_to_vram("qwen3-coder-next:latest"))
        expect(model == "qwen3-coder-next:latest", "plenty of VRAM -> keep the best model")
    check("vram-fit: big card keeps the heavy model", body)


def test_no_gpu_is_noop():
    def body():
        model, note = _with_env(None, SIZES,
                               lambda: copilot.fit_to_vram("qwen3-coder-next:latest"))
        expect(model == "qwen3-coder-next:latest", "unknown VRAM -> leave pick alone")
        expect(note is None, "no note without a VRAM reading")
    check("vram-fit: no measurable GPU -> no-op (safe default)", body)


def test_api_and_lms_untouched():
    def body():
        m1, _ = _with_env(16 * GB, SIZES, lambda: copilot.fit_to_vram("claude-opus-4-8"))
        m2, _ = _with_env(16 * GB, SIZES, lambda: copilot.fit_to_vram("lms/some-model"))
        expect(m1 == "claude-opus-4-8", "API models are never swapped")
        expect(m2 == "lms/some-model", "LM Studio models are never swapped")
    check("vram-fit: API + LM Studio models are exempt", body)


if __name__ == "__main__":
    print("== swap =="); test_swaps_oversized_model()
    print("== keep =="); test_keeps_fitting_model()
    print("== big card =="); test_big_card_keeps_big_model()
    print("== no gpu =="); test_no_gpu_is_noop()
    print("== exempt =="); test_api_and_lms_untouched()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
