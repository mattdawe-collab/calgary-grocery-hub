import json
import os
import sys

import pandas as pd
import pytest

import weekly_report_generator as wrg

FAKE = f'"{sys.executable}" "{os.path.join(os.path.dirname(__file__), "fake_claude.py")}"'


@pytest.fixture
def cli_report_backend(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_CMD", FAKE)
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "report")
    monkeypatch.setenv("AI_BACKEND", "claude_code")
    monkeypatch.setattr("ai_backends.claude_cli_logged_in", lambda: True)


def _report_data():
    return {
        "week_ending": "2026-09-16",
        "total_deals": 2,
        "score_col": "deal_score",
        "proteins": {"Pork": {"count": 1, "avg_score": 80, "deals": [
            {"item": "Bacon", "price": 4.99, "raw_price": 4.99, "store": "Sobeys", "score": 88,
             "context": {"context_text": "30% below avg", "pct_below_avg": 30}, "is_per_100g": False, "price_note": ""}]}},
        "categories": {"Produce": {"count": 1, "avg_score": 70, "deals": [
            {"item": "Grapes", "price": 2.49, "raw_price": 2.49, "store": "Co-op", "score": 75,
             "context": {"context_text": "lowest in 2 months", "pct_below_avg": 20}, "is_per_100g": False, "price_note": ""}]}},
        "stores": {"Sobeys": {"total_deals": 1, "avg_score": 80, "categories": {"Pork": {"count": 1, "avg_score": 80, "deals": [
            {"item": "Bacon", "price": 4.99, "raw_price": 4.99, "score": 88,
             "context": {"context_text": "30% below avg"}, "is_per_100g": False, "price_note": ""}]}}}},
        "top_deals": [],
    }


def test_week_ending_uses_common_flyer_end_not_outlier():
    df = pd.DataFrame({"Valid_Until": ["2026-09-16"] * 20 + ["2026-10-21"] * 3})
    assert wrg._week_ending(df) == "2026-09-16"


def test_week_ending_falls_back_to_today_when_missing():
    df = pd.DataFrame({"Item": ["x"]})
    assert wrg._week_ending(df) == pd.Timestamp.now().strftime("%Y-%m-%d")


def test_truncated_ai_report_is_rejected():
    assert wrg._report_looks_complete("Alright Calgary, here are the deals for the week ending Oct 21 ... $2.49 Green Peppers - 45% below avg $4") is False
    good = ("Real content line. " * 60) + "\n#YYCDeals #CalgaryGrocery"
    assert wrg._report_looks_complete(good) is True


def test_store_report_uses_template_when_ai_output_incomplete(monkeypatch):
    monkeypatch.setattr(wrg, "generate_store_report_ai", lambda data: "too short, cut off mid")
    text = wrg.generate_store_report(_report_data(), use_ai=True)
    assert "CALGARY GROCERY DEALS BY STORE" in text  # template header


def test_store_report_via_claude_cli(cli_report_backend):
    text = wrg.generate_store_report(_report_data(), use_ai=True)
    assert text.endswith("#YYCDeals #CalgaryGrocery #GroceryDeals")
    assert "Calgary deals this week" in text


def test_facebook_post_is_short_and_links_to_page(cli_report_backend, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_TEXT", "ignored in report mode")
    post = wrg.generate_facebook_post(_report_data(), page_url="https://example.test/deals/", use_ai=True)
    assert len(post) <= 2000
    assert "https://example.test/deals/" in post


def test_facebook_post_template_without_ai():
    post = wrg.generate_facebook_post(_report_data(), page_url="https://example.test/deals/", use_ai=False)
    assert len(post) <= 2000
    assert "Bacon" in post and "$4.99" in post
    assert "https://example.test/deals/" in post


def test_generate_weekly_reports_writes_latest_json(tmp_path, monkeypatch, cli_report_backend):
    monkeypatch.setattr(wrg, "load_data", lambda: (pd.DataFrame({
        "Store": ["Sobeys"], "Item": ["Bacon"], "Price_Value": [4.99], "Valid_Until": ["2026-09-16"],
        "deal_score": [88.0], "ai_category": ["Pork"], "display_category": ["Pork"],
    }), pd.DataFrame()))
    monkeypatch.setattr(wrg, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_DASHBOARD_URL", "https://example.test")
    wrg.generate_weekly_reports(use_ai=True)
    latest = json.loads((tmp_path / "weekly_reports_latest.json").read_text(encoding="utf-8"))
    assert latest["week_ending"] == "2026-09-16"
    assert latest["store_report"].endswith("#GroceryDeals")
    assert "https://example.test" in latest["facebook_post"]
    assert any(p.name.startswith("weekly_post_FACEBOOK_") for p in tmp_path.iterdir())


def test_clean_ai_post_drops_commentary_after_hashtags():
    raw = (
        "Deals line one.\nDeals line two.\n\n#YYCDeals #CalgaryGrocery\n\n---\n\n"
        "Notes:\n- The post is about 820 characters.\n- Today is Sept 22."
    )
    cleaned = wrg._clean_ai_post(raw)
    assert cleaned.endswith("#YYCDeals #CalgaryGrocery")
    assert "Notes" not in cleaned


def test_clean_ai_post_strips_markdown_bold_and_preamble():
    raw = "Here's your post:\n\n🛒 **CALGARY DEALS** 🛒\n• $5.99 **Bacon**: 30% below avg\n#YYCDeals"
    cleaned = wrg._clean_ai_post(raw)
    assert "**" not in cleaned
    assert not cleaned.startswith("Here's your post")
    assert cleaned.startswith("🛒 CALGARY DEALS")


def test_clean_ai_post_keeps_text_without_hashtags():
    assert wrg._clean_ai_post("plain text, no tags") == "plain text, no tags"


def test_week_ending_does_not_roll_past_midnight_on_offset_timestamps():
    # Flipp sends "2026-09-30T23:59:59-04:00". Converting that to UTC lands on
    # Oct 1 and told shoppers the deals ran a day longer than they did.
    df = pd.DataFrame({"Valid_Until": ["2026-09-30T23:59:59-04:00"] * 20})
    assert wrg._week_ending(df) == "2026-09-30"
