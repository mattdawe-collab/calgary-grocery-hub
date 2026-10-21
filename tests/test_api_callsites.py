import json
import sys

import pandas as pd
import pytest

import ai_quality_analyzer as aqa
import weekly_report_generator as wrg


class _Recorder:
    """Stand-in Anthropic client that captures the request."""

    def __init__(self, text='[]'):
        self.text = text
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = type("B", (), {"type": "text", "text": self.text})()
        return type("R", (), {"content": [block], "stop_reason": "end_turn"})()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_scoring_uses_the_current_sonnet_model(monkeypatch):
    rec = _Recorder('[{"item": "Bacon", "category": "Pork", "subcategory": "Bacon", '
                    '"normalized_name": "Bacon", "score": 80, "rating": "Good", "explanation": "x"}]')
    monkeypatch.delenv("ANTHROPIC_SCORING_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    out = aqa.call_ai_api([{"item": "Bacon", "price": 4.99, "store": "A"}], "{}",
                          {"type": "anthropic", "client": rec})
    assert out[0]["item"] == "Bacon"
    assert rec.calls[0]["model"] == "claude-sonnet-5-5"


def test_scoring_asks_for_enough_output_tokens(monkeypatch):
    rec = _Recorder('[]')
    aqa.call_ai_api([{"item": "x", "price": 1.0, "store": "A"}], "{}",
                    {"type": "anthropic", "client": rec})
    # 40 items of JSON needs room; the Gemini truncation bug started this way.
    assert rec.calls[0]["max_tokens"] >= 8000


def test_a_dead_backend_is_not_retried_five_times(monkeypatch):
    err = Exception("Error code: 400 - Your credit balance is too low to access the Anthropic API.")

    class Dead(_Recorder):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            raise err

    rec = Dead()
    out = aqa.call_ai_api([{"item": "x", "price": 1.0, "store": "A"}], "{}",
                          {"type": "anthropic", "client": rec})
    assert out is None
    assert len(rec.calls) == 1, "burned retries on a backend that cannot work"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def test_report_caches_the_shared_data_block(monkeypatch):
    rec = _Recorder("A long report. " * 80 + "\n#YYCDeals")
    monkeypatch.setattr(wrg, "select_backend", lambda verbose=False: {"type": "anthropic"})
    monkeypatch.setattr(wrg, "_anthropic_client", lambda: rec)
    wrg._generate_text_with_ai("INSTRUCTIONS HERE", kind="report", cache_prefix="DATA HERE")
    content = rec.calls[0]["messages"][0]["content"]
    assert isinstance(content, list) and len(content) == 2
    # The identical data goes first and carries the breakpoint; all three
    # reports share it, so only the first pays full price.
    assert content[0]["text"] == "DATA HERE"
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[1]["text"] == "INSTRUCTIONS HERE"
    assert "cache_control" not in content[1]
    assert rec.calls[0]["model"] == "claude-opus-5-5"


def test_report_without_a_cache_prefix_sends_a_plain_prompt(monkeypatch):
    rec = _Recorder("A long report. " * 80 + "\n#YYCDeals")
    monkeypatch.setattr(wrg, "select_backend", lambda verbose=False: {"type": "anthropic"})
    monkeypatch.setattr(wrg, "_anthropic_client", lambda: rec)
    wrg._generate_text_with_ai("JUST THIS", kind="report")
    content = rec.calls[0]["messages"][0]["content"]
    assert content == "JUST THIS" or (isinstance(content, list) and len(content) == 1)


def test_cli_backend_still_receives_the_data_and_the_instructions(monkeypatch):
    seen = {}
    monkeypatch.setattr(wrg, "select_backend", lambda verbose=False: {"type": "claude_code"})
    monkeypatch.setattr(wrg, "run_claude_cli", lambda prompt, model=None: seen.setdefault("p", prompt) or "ok")
    wrg._generate_text_with_ai("INSTRUCTIONS", kind="report", cache_prefix="DATA")
    assert "DATA" in seen["p"] and "INSTRUCTIONS" in seen["p"]


def _tiny_report_data():
    return {
        "week_ending": "2026-10-28", "total_deals": 2, "score_col": "deal_score",
        "proteins": {"Pork": {"count": 1, "avg_score": 80, "deals": [
            {"item": "Bacon", "price": 4.99, "raw_price": 4.99, "store": "Sobeys", "score": 88,
             "context": {"context_text": "30% below avg"}, "is_per_100g": False, "price_note": ""}]}},
        "categories": {}, "stores": {}, "top_deals": [],
    }


def test_all_three_reports_share_one_cached_data_block(monkeypatch):
    seen = []

    def fake(prompt, kind="report", temperature=0.8, cache_prefix=None):
        seen.append({"prompt": prompt, "cache_prefix": cache_prefix})
        return "Report body. " * 80 + "\n#YYCDeals"

    monkeypatch.setattr(wrg, "_generate_text_with_ai", fake)
    data = _tiny_report_data()
    wrg.generate_store_report(data, use_ai=True)
    wrg.generate_category_report(data, use_ai=True)
    wrg.generate_facebook_post(data, page_url="https://x.test/", use_ai=True)

    assert len(seen) == 3
    prefixes = {c["cache_prefix"] for c in seen}
    assert len(prefixes) == 1, "the three reports must send a byte-identical data block"
    prefix = prefixes.pop()
    assert prefix and "Bacon" in prefix, "the week's data belongs in the cached block"
    # The uncached instructions must not grow with the data: that is what
    # tells us the figures live only in the cached block. Re-run with 50x the
    # deals and the instruction halves should barely move.
    small = [len(c["prompt"]) for c in seen]
    seen.clear()
    big = _tiny_report_data()
    big["proteins"]["Pork"]["deals"] *= 50
    wrg.generate_store_report(big, use_ai=True)
    wrg.generate_category_report(big, use_ai=True)
    wrg.generate_facebook_post(big, page_url="https://x.test/", use_ai=True)
    grown_prefix = seen[0]["cache_prefix"]
    assert len(grown_prefix) > len(prefix) * 5, "the data block should carry the extra deals"
    for before, call in zip(small, seen):
        assert len(call["prompt"]) < before + 400, (
            "instructions grew with the data - the figures are being duplicated outside the cache"
        )


# ---------------------------------------------------------------------------
# Current models reject sampling parameters
# ---------------------------------------------------------------------------
def test_scoring_does_not_send_temperature():
    # claude-sonnet-5-5 returns 400 "`temperature` is deprecated for this
    # model". Sending it failed all 30 scoring batches on 2026-10-21.
    rec = _Recorder('[]')
    aqa.call_ai_api([{"item": "x", "price": 1.0, "store": "A"}], "{}",
                    {"type": "anthropic", "client": rec})
    assert "temperature" not in rec.calls[0]
    assert "top_p" not in rec.calls[0] and "top_k" not in rec.calls[0]


def test_reports_do_not_send_temperature(monkeypatch):
    # The same 400 would have hit claude-opus-5-5 on the three write-ups.
    rec = _Recorder("A long report. " * 80 + "\n#YYCDeals")
    monkeypatch.setattr(wrg, "select_backend", lambda verbose=False: {"type": "anthropic"})
    monkeypatch.setattr(wrg, "_anthropic_client", lambda: rec)
    wrg._generate_text_with_ai("INSTRUCTIONS", kind="report", temperature=0.8)
    assert "temperature" not in rec.calls[0]


def test_scoring_announces_the_model_it_will_actually_use(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_SCORING_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    aqa._make_ai_client("anthropic")
    out = capsys.readouterr().out
    assert "claude-sonnet-5-5" in out, f"log named a different model than the call uses: {out}"


# ---------------------------------------------------------------------------
# Thinking blocks come back first
# ---------------------------------------------------------------------------
def _block(kind, **kw):
    return type("B", (), {"type": kind, **kw})()


class _ThinkingRecorder(_Recorder):
    """Current models think by default, so content[0] is a ThinkingBlock.

    A ThinkingBlock has no .text, so reading content[0].text raised
    "'ThinkingBlock' object has no attribute 'text'" on every 40-item batch
    of the 2026-10-21 re-run. An 8-item test batch never triggered thinking,
    which is exactly why it slipped through.
    """

    def create(self, **kwargs):
        self.calls.append(kwargs)
        thinking = _block("thinking", thinking="Let me work through these items...")
        return type("R", (), {"content": [thinking, _block("text", text=self.text)]})()


def test_scoring_reads_past_a_leading_thinking_block():
    rec = _ThinkingRecorder('[{"item": "Bacon", "category": "Pork", "subcategory": "Bacon", '
                            '"normalized_name": "Bacon", "score": 80, "rating": "Good", "explanation": "x"}]')
    out = aqa.call_ai_api([{"item": "Bacon", "price": 4.99, "store": "A"}], "{}",
                          {"type": "anthropic", "client": rec})
    assert out is not None, "a thinking block made the whole batch fall back"
    assert out[0]["item"] == "Bacon"


def test_reports_read_past_a_leading_thinking_block(monkeypatch):
    rec = _ThinkingRecorder("A long report. " * 80 + "\n#YYCDeals")
    monkeypatch.setattr(wrg, "select_backend", lambda verbose=False: {"type": "anthropic"})
    monkeypatch.setattr(wrg, "_anthropic_client", lambda: rec)
    text = wrg._generate_text_with_ai("INSTRUCTIONS", kind="report")
    assert text and "A long report" in text
    assert "Let me work through" not in text, "thinking leaked into the published report"


def test_text_from_several_text_blocks_is_joined():
    from ai_backends import response_text

    r = type("R", (), {"content": [_block("thinking", thinking="..."),
                                   _block("text", text="part one "),
                                   _block("text", text="part two")]})()
    assert response_text(r) == "part one part two"


def test_response_text_is_empty_when_only_thinking_came_back():
    from ai_backends import response_text

    r = type("R", (), {"content": [_block("thinking", thinking="...")]})()
    assert response_text(r) == ""
