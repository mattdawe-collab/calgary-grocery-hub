import os
import sys

import pandas as pd
import pytest

import ai_quality_analyzer as aqa

FAKE = f'"{sys.executable}" "{os.path.join(os.path.dirname(__file__), "fake_claude.py")}"'


@pytest.fixture
def cli_backend(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_CMD", FAKE)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "echo_items")
    monkeypatch.delenv("FAKE_CLAUDE_DROP_LAST", raising=False)
    monkeypatch.setenv("AI_BACKEND", "claude_code")
    monkeypatch.setattr("ai_backends.claude_cli_logged_in", lambda: True)


def _frame(n):
    return pd.DataFrame({
        "Item": [f"Bacon {i}" for i in range(n)],
        "Price_Value": [4.99 + i for i in range(n)],
        "Store": ["A"] * n,
    })


def test_call_ai_api_uses_claude_cli_backend(cli_backend):
    batch = [{"item": "Bacon 1", "price": 4.99, "store": "A"}]
    result = aqa.call_ai_api(batch, "{}", {"type": "claude_code"})
    assert result[0]["item"] == "Bacon 1"
    assert result[0]["score"] == 77


def test_results_are_matched_by_item_name_not_position(cli_backend):
    df = aqa.add_ai_analysis_to_dataframe(_frame(3), None, batch_size=3)
    assert (df["ai_confidence"] == "claude_code").all()
    assert (df["ai_category"] == "Pork").all()
    assert list(df["ai_deal_score"]) == [77, 77, 77]


def test_missing_items_fall_back_individually(cli_backend, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_DROP_LAST", "1")
    df = aqa.add_ai_analysis_to_dataframe(_frame(3), None, batch_size=3)
    # Fake drops the first-listed item's result (it's last after reversal),
    # so exactly one row should be statistical, the rest from the CLI.
    assert (df["ai_confidence"] == "claude_code").sum() == 2
    assert (df["ai_confidence"] == "statistical").sum() == 1


def test_parallel_batches_keep_rows_aligned(cli_backend, monkeypatch):
    monkeypatch.setenv("AI_WORKERS", "3")
    df = aqa.add_ai_analysis_to_dataframe(_frame(10), None, batch_size=2)
    assert (df["ai_confidence"] == "claude_code").all()
    assert len(df) == 10


def test_statistical_backend_never_calls_cli(monkeypatch):
    monkeypatch.setenv("AI_BACKEND", "statistical")
    monkeypatch.setenv("CLAUDE_CLI_CMD", FAKE)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "crash")
    df = aqa.add_ai_analysis_to_dataframe(_frame(2), None, batch_size=2)
    assert (df["ai_confidence"] == "statistical").all()


def test_gemini_config_disables_thinking_and_forces_json():
    cfg = aqa._gemini_scoring_config()
    assert cfg["thinking_config"]["thinking_budget"] == 0
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["max_output_tokens"] >= 16000
