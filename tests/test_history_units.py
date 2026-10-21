import pandas as pd

from get_deals import compute_historical_stats
from tools.weekly_page import build_page_model

RECENT = (pd.Timestamp.now() - pd.Timedelta(days=20)).strftime("%Y-%m-%d")


def _history():
    rows = [{"Date": RECENT, "Store": "No Frills", "Item": "CHICKEN BREASTS, 800 G",
             "Price_Value": p, "ai_category": "Poultry", "ai_normalized_name": "Chicken Breasts",
             "unit_price": u, "unit_type": "$/kg", "price_basis": "each"}
            for p, u in [(17.0, 21.25), (18.0, 22.50), (16.0, 20.00)]]
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def _current():
    return pd.DataFrame([{
        "Store": "No Frills", "Item": "CHICKEN BREASTS, 800 G", "Price_Value": 13.00,
        "ai_category": "Poultry", "ai_normalized_name": "Chicken Breasts",
        "unit_price": 16.25, "unit_type": "$/kg", "price_basis": "each",
    }])


def test_history_records_the_unit_it_was_compared_in():
    # The average here is $/kg while the price is a package price. Without a
    # marker the page prints "$13.00, usually $21.25" and looks broken.
    out = compute_historical_stats(_current(), _history())
    assert out.loc[0, "history_unit"] == "$/kg"
    assert 20 < out.loc[0, "historical_avg"] < 23


def test_package_comparisons_are_marked_as_such():
    hist = _history()
    hist["unit_price"] = None
    cur = _current()
    cur["unit_price"] = None
    out = compute_historical_stats(cur, hist)
    assert out.loc[0, "history_unit"] == ""
    assert 15 < out.loc[0, "historical_avg"] < 19


def test_page_labels_a_per_kilogram_average():
    row = {
        "Store": "No Frills", "Item": "CHICKEN BREASTS, 800 G", "Price_Value": 13.00,
        "display_category": "Poultry", "deal_score": 90.0, "historical_avg": 21.25,
        "history_unit": "$/kg", "pct_below_avg": 23.0, "historical_count": 3,
        "is_lowest_historical": False, "cross_store_rank": 1, "cross_store_count": 1,
        "action_label": "Buy this week", "why_bullets": "23% below avg",
        "Valid_From": "2026-10-01", "Valid_Until": "2026-10-07",
        "confidence_score": 80, "unit_price": 16.25, "unit_type": "$/kg",
        "price_basis": "each",
    }
    model = build_page_model(pd.DataFrame([row], index=[1]), None, "https://x.test/")
    assert model["deals"][0]["avg_label"] == "$21.25/kg"
