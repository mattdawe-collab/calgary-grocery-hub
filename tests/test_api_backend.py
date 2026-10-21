import pytest

import ai_backends
from ai_backends import (
    anthropic_model,
    is_backend_unusable,
    select_backend,
    verify_backend,
)


# ---------------------------------------------------------------------------
# Backend order: the API is the primary now
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("AI_BACKEND", "AI_ALLOW_PAID_FALLBACK", "ANTHROPIC_API_KEY",
                "GEMINI_API_KEY", "CLAUDE_CLI_CMD", "ANTHROPIC_SCORING_MODEL",
                "ANTHROPIC_REPORT_MODEL", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ai_backends, "claude_cli_logged_in", lambda: False)
    monkeypatch.setattr(ai_backends, "claude_cli_command", lambda: None)


def test_auto_prefers_the_api_when_a_key_is_present(monkeypatch):
    # The CLI login expired twice and killed a Wednesday run; an API key does
    # not expire, so it leads now.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert select_backend()["type"] == "anthropic"


def test_auto_falls_back_to_the_cli_when_there_is_no_key(monkeypatch):
    monkeypatch.setattr(ai_backends, "claude_cli_command", lambda: ["claude"])
    monkeypatch.setattr(ai_backends, "claude_cli_logged_in", lambda: True)
    assert select_backend()["type"] == "claude_code"


def test_auto_falls_back_to_statistical_when_nothing_is_available():
    assert select_backend()["type"] == "statistical"


def test_the_api_no_longer_needs_the_paid_fallback_opt_in(monkeypatch):
    # That flag existed to prevent surprise billing while the CLI was primary.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("AI_ALLOW_PAID_FALLBACK", "0")
    assert select_backend()["type"] == "anthropic"


def test_gemini_still_requires_being_asked_for_by_name(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    assert select_backend()["type"] == "statistical"
    monkeypatch.setenv("AI_BACKEND", "gemini")
    assert select_backend()["type"] == "gemini"


# ---------------------------------------------------------------------------
# Verification: a key that exists is not a key that works
# ---------------------------------------------------------------------------
class _FakeMessages:
    def __init__(self, error=None):
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error

        class R:
            content = [type("B", (), {"type": "text", "text": "OK"})()]
        return R()


class _FakeClient:
    def __init__(self, error=None):
        self.messages = _FakeMessages(error)


def test_verify_accepts_a_working_key():
    ok, reason = verify_backend("anthropic", client=_FakeClient())
    assert ok is True
    assert reason == ""


def test_verify_rejects_a_key_with_no_credit_balance():
    # The exact failure on this account: the key authenticates, then every
    # call 400s. "Key is set" was never proof the backend works.
    err = Exception("Error code: 400 - Your credit balance is too low to access the Anthropic API.")
    ok, reason = verify_backend("anthropic", client=_FakeClient(err))
    assert ok is False
    assert "credit" in reason.lower()


def test_verify_spends_almost_nothing():
    client = _FakeClient()
    verify_backend("anthropic", client=client)
    assert client.messages.calls[0]["max_tokens"] <= 16


def test_credit_and_auth_failures_are_permanent_not_retryable():
    assert is_backend_unusable(Exception("Your credit balance is too low")) is True
    assert is_backend_unusable(Exception("401 authentication_error: invalid x-api-key")) is True
    assert is_backend_unusable(Exception("403 permission_denied")) is True
    # A rate limit or a blip is worth retrying, not a backend swap.
    assert is_backend_unusable(Exception("429 rate_limit_error")) is False
    assert is_backend_unusable(Exception("529 overloaded_error")) is False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def test_default_models_are_the_current_generation(monkeypatch):
    assert anthropic_model("scoring") == "claude-sonnet-5-5"
    assert anthropic_model("report") == "claude-opus-5-5"


def test_models_are_overridable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_SCORING_MODEL", "claude-haiku-5-5")
    assert anthropic_model("scoring") == "claude-haiku-5-5"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5-5")
    monkeypatch.delenv("ANTHROPIC_SCORING_MODEL")
    assert anthropic_model("scoring") == "claude-opus-5-5"


def test_the_real_client_constructor_is_importable(monkeypatch):
    # verify_backend() builds its own client when none is injected. That path
    # had an undefined name and every fake-client test sailed past it.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-real")
    ok, reason = verify_backend("anthropic")
    assert ok is False
    assert "not defined" not in reason, f"construction path is broken: {reason}"
    assert "NameError" not in reason


def test_verification_sends_the_same_request_shape_as_real_scoring():
    """Preflight must fail when real calls would fail.

    On 2026-10-21 verification passed and all 30 scoring batches then 400'd,
    because verification sent a different set of parameters than the scoring
    call did. Both now build the request through one function, so a parameter
    the model rejects breaks preflight instead of the whole run.
    """
    import ai_quality_analyzer as aqa
    from ai_backends import anthropic_request_kwargs

    verify_client = _FakeClient()
    verify_backend("anthropic", client=verify_client)

    class Rec(_FakeClient):
        def __init__(self):
            super().__init__()
            self.messages = self
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            block = type("B", (), {"type": "text", "text": "[]"})()
            return type("R", (), {"content": [block]})()

    rec = Rec()
    aqa.call_ai_api([{"item": "x", "price": 1.0, "store": "A"}], "{}",
                    {"type": "anthropic", "client": rec})

    assert set(verify_client.messages.calls[0]) == set(rec.calls[0]), (
        "verification and scoring send different parameters, so preflight "
        "cannot prove scoring will work"
    )
    assert "temperature" not in anthropic_request_kwargs("m", "s", "p", 10)


def test_scoring_requests_low_effort_but_reports_do_not():
    """Classification does not repay deep thinking.

    Measured on a real 40-item batch: default effort took 31.7s and 6,362
    output tokens, low effort 21.1s and 4,584, with identical results. The
    write-ups are narrative work and keep the model's default.
    """
    from ai_backends import anthropic_request_kwargs

    scoring = anthropic_request_kwargs("claude-sonnet-5-5", "s", "p", 16384, effort="low")
    assert scoring["output_config"] == {"effort": "low"}

    report = anthropic_request_kwargs("claude-opus-5-5", "s", "p", 16000)
    assert "output_config" not in report
