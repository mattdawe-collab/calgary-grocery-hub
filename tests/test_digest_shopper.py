import pandas as pd

import send_telegram_digest as std


def _deals():
    rows = [
        {"Item": "Canada Grade A Turkey", "Store": "Sobeys", "Price_Value": 2.19,
         "display_category": "Poultry", "deal_score": 95.0, "action_label": "Stock up",
         "price_basis": "each", "unit_price": None, "unit_type": None, "confidence_score": 80},
        {"Item": "Canada Grade A Turkey", "Store": "Safeway", "Price_Value": 2.19,
         "display_category": "Poultry", "deal_score": 95.0, "action_label": "Stock up",
         "price_basis": "each", "unit_price": None, "unit_type": None, "confidence_score": 80},
        {"Item": "Canada Grade A Turkey", "Store": "Calgary Co-op", "Price_Value": 2.49,
         "display_category": "Poultry", "deal_score": 90.0, "action_label": "Buy this week",
         "price_basis": "each", "unit_price": None, "unit_type": None, "confidence_score": 80},
    ]
    return pd.DataFrame(rows)


def test_digest_collapses_sister_banners(monkeypatch):
    monkeypatch.setattr(std, "_prepare_current_deals", lambda: _deals().assign(
        Valid_From="2026-10-01", Valid_Until="2026-10-07", ai_confidence="claude_code"))
    text = std.build_digest(limit=10, min_score=50)
    assert text.count("Canada Grade A Turkey") == 2      # Empire collapsed, Co-op kept
    assert "Safeway" in text or "Sobeys" in text


def test_digest_labels_per_pound_meat(monkeypatch):
    monkeypatch.setattr(std, "_prepare_current_deals", lambda: _deals().assign(
        Valid_From="2026-10-01", Valid_Until="2026-10-07", ai_confidence="claude_code"))
    text = std.build_digest(limit=10, min_score=50)
    assert "$2.19/lb" in text, "per-pound turkey shown as a bare price"
