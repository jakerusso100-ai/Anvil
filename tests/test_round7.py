"""Round 7 — regression tests for the 3 bugs found by the user stress-audit.

These are first-run / failure-path bugs the earlier suites missed because they
only exercised happy paths. Run: py -3.14 -X utf8 tests/test_round7.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from test_anvil import FAIL, check, expect  # noqa: E402

import agent  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402


def test_pipeline_coder_failure():
    """BUG: an API coder model that fails (no key/network) crashed run_turn."""

    def boom_stream(model, messages, system=None):
        raise RuntimeError("simulated API auth failure")
        yield  # unreachable

    def coder_fails_cleanly():
        real = llm.stream_chat
        llm.stream_chat = boom_stream
        try:
            evs = list(pipeline.run_turn(model="claude-haiku-4-5",
                                         messages=[{"role": "user", "content": "hi"}],
                                         review=False))
        finally:
            llm.stream_chat = real
        expect(evs[-1]["type"] == "final", "must still yield a final")
        expect(any(e["type"] == "review_error" for e in evs), "must report the error")
    check("pipeline: coder failure -> clean error, no crash", coder_fails_cleanly)

    def revision_fails_cleanly():
        # coder succeeds with code, review says revise, then revision stream fails
        calls = {"n": 0}

        def flaky_stream(model, messages, system=None):
            calls["n"] += 1
            if calls["n"] == 1:
                yield {"type": "delta", "text": "```python\ndef f(): return 1\n```"}
                yield {"type": "done", "usage": llm.Usage(1, 1, 0)}
            else:
                raise RuntimeError("revision network drop")

        def mock_review(reviewer, req, produced):
            return ({"verdict": "revise", "summary": "x", "issues": [],
                     "revision_instruction": "fix"}, llm.Usage(1, 1, 0))

        rs, rr = llm.stream_chat, llm.review_code
        llm.stream_chat, llm.review_code = flaky_stream, mock_review
        try:
            evs = list(pipeline.run_turn(model="m", messages=[{"role": "user", "content": "code"}],
                                         review=True, reviewer="r", auto_revise=True, max_rounds=3))
        finally:
            llm.stream_chat, llm.review_code = rs, rr
        expect(evs[-1]["type"] == "final", "must yield final after revision failure")
        expect(any(e["type"] == "review_error" for e in evs), "must report revision error")
    check("pipeline: revision failure -> clean error, no crash", revision_fails_cleanly)


def test_agent_wrapper_never_raises():
    """BUG: run_agent could propagate an unhandled exception to the caller."""

    def bad_dispatch(*a, **k):
        raise RuntimeError("simulated dispatch explosion")
        yield

    def wrapper_guards():
        real = agent._dispatch_agent
        agent._dispatch_agent = bad_dispatch
        try:
            evs = list(agent.run_agent("any-model", [{"role": "user", "content": "hi"}],
                                       tempfile.mkdtemp()))
        finally:
            agent._dispatch_agent = real
        expect(evs[-1]["type"] == "final", "must always end on a final")
        expect(any(e["type"] == "final_text" and "error" in e["answer"].lower() for e in evs),
               "must surface the error text")
    check("agent: run_agent never raises to caller", wrapper_guards)

    def unknown_ollama_model():
        # a genuinely unknown local model: the ollama call fails, must end clean
        evs = list(agent.run_agent("no-such-model-zzz:latest",
                                   [{"role": "user", "content": "hi"}], tempfile.mkdtemp()))
        expect(evs[-1]["type"] == "final", "unknown model must end clean")
    check("agent: unknown local model -> clean final", unknown_ollama_model)


def test_first_run_health():
    """Health check must be honest and non-crashing with nothing configured."""
    import copilot
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        h = copilot.health()
        names = {i["name"] for i in h}
        expect({"Ollama", "Roster", "API"} <= names, "core components present")
        api = next(i for i in h if i["name"] == "API")
        expect(not api["ok"], "API should read as not-ok without a key")
    finally:
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old
    check("health: honest with no API key", lambda: True)


def test_ollama_step_hardening():
    """A transient Ollama 500 or hang must retry once (not kill the build); a 4xx
    fails fast. This is the gap the chess stress reruns exposed."""
    import requests as _rq

    class FakeResp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload or {}
            self.response = self

        def raise_for_status(self):
            if self.status_code >= 400:
                err = _rq.HTTPError(str(self.status_code))
                err.response = self
                raise err

        def json(self):
            return self._payload

    def retry_on_500():
        calls = {"n": 0}

        def fake_post(url, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResp(500)
            return FakeResp(200, {"message": {"role": "assistant", "content": "ok"}})
        real = agent.requests.post
        agent.requests.post = fake_post
        try:
            m = agent._ollama_step("gpt-oss:20b", [{"role": "user", "content": "hi"}])
        finally:
            agent.requests.post = real
        expect(calls["n"] == 2, "a 500 triggers exactly one retry")
        expect(m["content"] == "ok", "the retry's result is returned")
    check("ollama-step: retries once on a transient 500", retry_on_500)

    def fail_fast_on_400():
        calls = {"n": 0}

        def fake_post(url, **k):
            calls["n"] += 1
            return FakeResp(400)
        real = agent.requests.post
        agent.requests.post = fake_post
        try:
            raised = False
            try:
                agent._ollama_step("m", [{"role": "user", "content": "hi"}])
            except _rq.HTTPError:
                raised = True
        finally:
            agent.requests.post = real
        expect(raised, "a 4xx propagates")
        expect(calls["n"] == 1, "a 4xx is not retried")
    check("ollama-step: 4xx fails fast (no retry)", fail_fast_on_400)

    def retry_on_hang():
        calls = {"n": 0}

        def fake_post(url, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _rq.Timeout("read timed out")
            return FakeResp(200, {"message": {"role": "assistant", "content": "recovered"}})
        real = agent.requests.post
        agent.requests.post = fake_post
        try:
            m = agent._ollama_step("m", [{"role": "user", "content": "hi"}])
        finally:
            agent.requests.post = real
        expect(m["content"] == "recovered", "recovers after a single hang")
        expect(calls["n"] == 2, "a hang is retried once")
    check("ollama-step: retries once on a hang (timeout)", retry_on_hang)


if __name__ == "__main__":
    print("== pipeline failure paths =="); test_pipeline_coder_failure()
    print("== agent wrapper guard =="); test_agent_wrapper_never_raises()
    print("== first-run health =="); test_first_run_health()
    print("== ollama step hardening =="); test_ollama_step_hardening()
    import test_anvil
    print(f"\n{test_anvil.PASS} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print(f"  FAILED: {name} -> {err}")
    sys.exit(1 if FAIL else 0)
