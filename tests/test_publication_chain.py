import argparse

import pytest

from tools import run_publication_chain as chain


def test_preflight_raises_when_no_ai_backend(monkeypatch):
    monkeypatch.delenv("AI_REQUIRE_BACKEND", raising=False)
    monkeypatch.setattr(chain, "usable_backend", lambda verbose=False: {
        "type": "statistical", "reason": "x",
        "attempts": [{"backend": "claude_code", "ok": False, "reason": "run `claude login`"}]})
    with pytest.raises(chain.ChainError, match="claude login"):
        chain.preflight_ai_backend()


def test_preflight_passes_with_claude_cli(monkeypatch):
    monkeypatch.setattr(chain, "usable_backend", lambda verbose=False: {
        "type": "claude_code", "reason": "verified", "attempts": []})
    assert chain.preflight_ai_backend() == "claude_code"


def test_preflight_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI_REQUIRE_BACKEND", "0")
    monkeypatch.setattr(chain, "usable_backend", lambda verbose=False: {
        "type": "statistical", "reason": "x", "attempts": []})
    assert chain.preflight_ai_backend() == "statistical"


def test_send_alert_goes_to_private_alert_chat_only(monkeypatch):
    monkeypatch.setattr(chain, "ENV_FILE_VALUES", {})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@PublicChannel")
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "123456")
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        class R:
            def raise_for_status(self): pass
            def json(self): return {"ok": True}
        return R()

    assert chain.send_alert("Weekly run failed", post=fake_post) is True
    assert calls[0][1]["chat_id"] == "123456"
    assert "@PublicChannel" not in str(calls)


def test_send_alert_skips_when_no_alert_chat(monkeypatch, capsys):
    # _config also falls back to .env, so blank that too for this test.
    monkeypatch.setattr(chain, "ENV_FILE_VALUES", {})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@PublicChannel")
    monkeypatch.delenv("TELEGRAM_ALERT_CHAT_ID", raising=False)
    called = []
    assert chain.send_alert("x", post=lambda *a, **k: called.append(1)) is False
    assert not called
    assert "TELEGRAM_ALERT_CHAT_ID" in capsys.readouterr().out


def test_main_alerts_and_stops_when_preflight_fails(monkeypatch):
    alerts = []
    monkeypatch.setattr(chain, "parse_args", lambda: argparse.Namespace(
        skip_scrape=False, skip_reports=False, skip_data_push=True, skip_snapshot_publish=True,
        skip_telegram=True, dry_run_telegram=False, telegram_main=False, telegram_group=None,
        base_url="https://example.test", push_ref="HEAD:main", verify_deal_id=None, verify_marker="x",
        pages_timeout=1, pages_check_interval=1, output_dir=chain.DEFAULT_OUTPUT, skip_ai_preflight=False))
    monkeypatch.setattr(chain, "remote_url", lambda: "https://github.com/x/y.git")
    monkeypatch.setattr(chain, "preflight_ai_backend", lambda: (_ for _ in ()).throw(chain.ChainError("AI backend unavailable: run `claude login`")))
    monkeypatch.setattr(chain, "send_alert", lambda text, **kw: alerts.append(text) or True)
    ran = []
    monkeypatch.setattr(chain, "run_step", lambda *a, **k: ran.append(a[0]))
    assert chain.main() == 1
    assert ran == []                      # nothing scraped or published
    assert any("claude login" in a for a in alerts)


def test_run_summary_reports_health_not_just_completion(tmp_path, monkeypatch):
    import json

    import pandas as pd

    deals = pd.DataFrame({
        "Item": ["a", "b", "c", "d"],
        "deal_score": [95.0, 82.0, 40.0, 10.0],
        "ai_confidence": ["claude_code", "claude_code", "cached", "statistical"],
        "Valid_From": ["2026-09-24T03:00:00-04:00"] * 4,
        "Valid_Until": ["2026-09-30T23:59:59-04:00"] * 4,
    })
    deals.to_csv(tmp_path / "current_flyers.csv", index=False)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "weekly_reports_latest.json").write_text(
        json.dumps({"week_ending": "2026-09-30"}), encoding="utf-8"
    )
    monkeypatch.setattr(chain, "ROOT", tmp_path)

    text = chain.run_summary("https://x.test", elapsed_minutes=18)

    assert "4" in text and "2 worth a trip" in text      # deal counts
    assert "2026-09-24" in text and "2026-09-30" in text  # the flyer window
    assert "1 fallback" in text                           # scoring health
    assert "https://x.test" in text


def test_run_summary_flags_a_bad_scoring_run(tmp_path, monkeypatch):
    import pandas as pd

    pd.DataFrame({
        "Item": ["a", "b"],
        "deal_score": [50.0, 50.0],
        "ai_confidence": ["statistical", "statistical"],
        "Valid_From": ["2026-09-24"] * 2,
        "Valid_Until": ["2026-09-30"] * 2,
    }).to_csv(tmp_path / "current_flyers.csv", index=False)
    monkeypatch.setattr(chain, "ROOT", tmp_path)

    text = chain.run_summary("https://x.test", elapsed_minutes=3)
    assert "WARNING" in text.upper()


def test_run_summary_survives_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    text = chain.run_summary("https://x.test", elapsed_minutes=1)
    assert "https://x.test" in text        # still reports something usable


@pytest.mark.parametrize("failure", [AttributeError("date parsing failed"), OSError("disk unavailable")])
def test_main_alerts_on_unexpected_snapshot_failure(monkeypatch, failure):
    alerts, sends = [], []
    monkeypatch.setattr(chain, "parse_args", lambda: argparse.Namespace(
        skip_scrape=True, skip_reports=True, skip_data_push=True,
        skip_snapshot_publish=False, skip_telegram=False, skip_ai_preflight=True,
        base_url="https://example.test", output_dir=chain.DEFAULT_OUTPUT))
    monkeypatch.setattr(chain, "remote_url", lambda: "https://github.com/x/y.git")
    monkeypatch.setattr(chain, "generate", lambda *a: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(chain, "send_alert", lambda text: alerts.append(text) or True)
    monkeypatch.setattr(chain, "send_telegram_messages", lambda *a: sends.append(a))
    assert chain.main() == 1
    assert len(alerts) == 1
    assert str(failure) in alerts[0]
    assert not sends


def test_preflight_verifies_the_backend_rather_than_trusting_the_environment(monkeypatch):
    # A key with no credit balance passes every environment check and then
    # fails every call. Preflight must prove the backend answers.
    monkeypatch.setattr(chain, "usable_backend", lambda verbose=False: {
        "type": "statistical", "reason": "no AI backend verified",
        "attempts": [{"backend": "anthropic", "ok": False,
                      "reason": "Anthropic API key has no credit balance"}],
    })
    with pytest.raises(chain.ChainError, match="credit balance"):
        chain.preflight_ai_backend()


def test_preflight_falls_through_to_a_working_backend(monkeypatch):
    monkeypatch.setattr(chain, "usable_backend", lambda verbose=False: {
        "type": "claude_code", "reason": "verified",
        "attempts": [{"backend": "anthropic", "ok": False, "reason": "no credit balance"},
                     {"backend": "claude_code", "ok": True, "reason": ""}],
    })
    assert chain.preflight_ai_backend() == "claude_code"


def test_run_summary_names_the_backend_that_ran(tmp_path, monkeypatch):
    import pandas as pd
    pd.DataFrame({
        "Item": ["a", "b"], "deal_score": [95.0, 50.0],
        "ai_confidence": ["anthropic", "anthropic"],
        "Valid_From": ["2026-10-22"] * 2, "Valid_Until": ["2026-10-28"] * 2,
    }).to_csv(tmp_path / "current_flyers.csv", index=False)
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    text = chain.run_summary("https://x.test", elapsed_minutes=12, backend="anthropic")
    assert "anthropic" in text


def test_env_file_values_reach_the_chains_own_process(monkeypatch, tmp_path):
    """The chain evaluates the preflight in-process, so .env must be in os.environ.

    It only ever merged .env into the environment it handed to subprocesses.
    The preflight then read os.environ, found no ANTHROPIC_API_KEY, and
    stopped the run even though the key was sitting in .env.
    """
    import importlib
    import os

    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-from-dotenv\nPOSTAL_CODE=T3M1M9\n", encoding="utf-8-sig")
    monkeypatch.setattr(chain, "ROOT", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    chain.load_env_file_into_environ(tmp_path / ".env")
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-from-dotenv"
    assert os.environ.get("POSTAL_CODE") == "T3M1M9"


def test_a_real_environment_variable_still_wins_over_the_file(monkeypatch, tmp_path):
    import os

    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=sk-ant-from-dotenv\n", encoding="utf-8-sig")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    chain.load_env_file_into_environ(env)
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-shell"
