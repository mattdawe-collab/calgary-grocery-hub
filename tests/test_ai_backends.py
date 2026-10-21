import json
import os
import sys

import pytest

import ai_backends
from ai_backends import (
    ClaudeCLIError,
    claude_cli_env,
    extract_json_array,
    run_claude_cli,
    select_backend,
)

FAKE = f'"{sys.executable}" "{os.path.join(os.path.dirname(__file__), "fake_claude.py")}"'


@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    record = tmp_path / "record.json"
    monkeypatch.setenv("CLAUDE_CLI_CMD", FAKE)
    monkeypatch.setenv("FAKE_CLAUDE_RECORD", str(record))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_TEXT", raising=False)
    return record


def test_run_claude_cli_returns_result_text(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_TEXT", "hello world")
    assert run_claude_cli("say hi", model="opus") == "hello world"


def test_run_claude_cli_passes_headless_flags_and_model(fake_cli):
    run_claude_cli("prompt text", model="opus")
    args = json.loads(fake_cli.read_text())["args"]
    assert "-p" in args
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--output-format") + 1] == "json"
    assert "--no-session-persistence" in args
    assert args[args.index("--tools") + 1] == ""
    assert "--bare" not in args            # --bare skips the stored login
    # The prompt must travel over stdin: the .cmd shim goes through cmd.exe,
    # which caps argv (~8 KB) and truncates an argument at its first newline.
    assert "prompt text" not in args
    rec = json.loads(fake_cli.read_text())
    assert rec["stdin_head"].startswith("prompt text")


def test_run_claude_cli_scrubs_api_keys_and_nested_session_vars(fake_cli, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    run_claude_cli("x", model="opus")
    env = json.loads(fake_cli.read_text())["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_SESSION_ID" not in env


def test_run_claude_cli_raises_on_auth_error(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "auth_error")
    with pytest.raises(ClaudeCLIError, match="authenticate"):
        run_claude_cli("x", model="opus")


def test_run_claude_cli_raises_on_nonzero_exit(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    with pytest.raises(ClaudeCLIError, match="exit code 1"):
        run_claude_cli("x", model="opus")


def test_run_claude_cli_times_out(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "hang")
    with pytest.raises(ClaudeCLIError, match="timed out"):
        run_claude_cli("x", model="opus", timeout=2)


def test_claude_cli_env_keeps_unrelated_vars(monkeypatch):
    monkeypatch.setenv("POSTAL_CODE", "T3M1M9")
    env = claude_cli_env()
    assert env["POSTAL_CODE"] == "T3M1M9"


@pytest.mark.parametrize(
    "text",
    [
        '[{"item": "Bacon", "score": 80}]',
        '```json\n[{"item": "Bacon", "score": 80}]\n```',
        'Here you go:\n[{"item": "Bacon", "score": 80}]\nHope that helps!',
    ],
)
def test_extract_json_array_handles_fences_and_prose(text):
    assert extract_json_array(text) == [{"item": "Bacon", "score": 80}]


def test_extract_json_array_rejects_truncated_output():
    with pytest.raises(ValueError):
        extract_json_array('[{"item": "Bacon", "sco')


def test_select_backend_honours_explicit_setting(monkeypatch):
    monkeypatch.setenv("AI_BACKEND", "statistical")
    assert select_backend()["type"] == "statistical"


def test_select_backend_uses_the_cli_when_there_is_no_api_key(monkeypatch, fake_cli):
    # The API leads now; the CLI is the standby for when no key is configured.
    monkeypatch.delenv("AI_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_backends, "claude_cli_logged_in", lambda: True)
    assert select_backend()["type"] == "claude_code"


def test_select_backend_falls_to_statistical_when_cli_not_logged_in(monkeypatch, fake_cli):
    monkeypatch.delenv("AI_BACKEND", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_backends, "claude_cli_logged_in", lambda: False)
    assert select_backend()["type"] == "statistical"


def test_gemini_still_needs_the_paid_opt_in_but_anthropic_does_not(monkeypatch, fake_cli):
    # Switching to API credits was deliberate, so the Anthropic key no longer
    # needs an opt-in. Gemini stays off by default (its project hit a cap).
    monkeypatch.delenv("AI_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.delenv("AI_ALLOW_PAID_FALLBACK", raising=False)
    monkeypatch.setattr(ai_backends, "claude_cli_logged_in", lambda: False)
    assert select_backend()["type"] == "anthropic"

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "g-x")
    assert select_backend()["type"] == "statistical"


def test_default_models_split_sonnet_scoring_opus_reports(monkeypatch):
    for var in ("CLAUDE_CODE_MODEL", "CLAUDE_CODE_SCORING_MODEL", "CLAUDE_CODE_REPORT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert ai_backends.claude_cli_model("scoring") == "sonnet"
    assert ai_backends.claude_cli_model("report") == "opus"
    monkeypatch.setenv("CLAUDE_CODE_MODEL", "haiku")
    assert ai_backends.claude_cli_model("scoring") == "haiku"
    monkeypatch.setenv("CLAUDE_CODE_REPORT_MODEL", "opus")
    assert ai_backends.claude_cli_model("report") == "opus"


def test_run_claude_cli_uses_local_cwd_not_unc(fake_cli, monkeypatch):
    # claude.cmd runs under cmd.exe, which refuses a UNC working directory
    # ("UNC paths are not supported. Defaulting to Windows directory.").
    run_claude_cli("x", model="opus")
    cwd = json.loads(fake_cli.read_text())["cwd"]
    assert not cwd.startswith("\\\\") and not cwd.startswith("//")
    assert os.path.isdir(cwd)


def test_run_claude_cli_passes_large_multiline_prompt_intact(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_TEXT", "ok")
    prompt = "line one" + chr(10) + ("x" * 120 + chr(10)) * 1500      # ~180 KB, many newlines
    assert run_claude_cli(prompt, model="sonnet") == "ok"
    rec = json.loads(fake_cli.read_text())
    assert rec["stdin_len"] == len(prompt)
    assert rec["stdin_head"].startswith("line one")
