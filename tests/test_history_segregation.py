import pandas as pd

from get_deals import compute_historical_stats


RECENT = (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")


def _turkey_history():
    """Real shape of the archive: per-pound listings plus a few whole birds.

    Dates must sit inside the 180-day scoring window or nothing matches.
    """
    rows = [{"Date": RECENT, "Store": "Sobeys", "Item": "Grade A Turkey",
             "Price_Value": p, "ai_category": "Poultry", "ai_normalized_name": "Turkey",
             "unit_price": None, "price_basis": "each"} for p in [2.19, 2.49, 2.99, 2.29, 2.79]]
    rows += [{"Date": RECENT, "Store": "Real Canadian Superstore",
              "Item": "UTILITY GRADE FROZEN TURKEYS, 3-5 KG", "Price_Value": p,
              "ai_category": "Poultry", "ai_normalized_name": "Turkey",
              "unit_price": 3.60, "price_basis": "each"} for p in [18.0, 23.0, 30.0, 35.0]]
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def _current(item, price, unit_price=None):
    return pd.DataFrame([{
        "Store": "Sobeys", "Item": item, "Price_Value": price,
        "ai_category": "Poultry", "ai_normalized_name": "Turkey",
        "unit_price": unit_price, "price_basis": "each", "unit_type": None,
    }])


def test_per_pound_turkey_is_not_measured_against_whole_birds():
    # The bug: $2.19/lb vs an average dragged up by $18-$35 whole birds
    # produced "85% below average" and a perfect score.
    out = compute_historical_stats(_current("Canada Grade A Turkey", 2.19), _turkey_history())
    avg = out.loc[0, "historical_avg"]
    assert avg is not None and avg < 4, f"average {avg} still includes whole-bird prices"
    assert out.loc[0, "pct_below_avg"] < 30


def test_whole_bird_is_measured_against_whole_birds():
    out = compute_historical_stats(
        _current("UTILITY GRADE FROZEN TURKEYS, 3-5 KG", 18.00, unit_price=3.60), _turkey_history()
    )
    avg = out.loc[0, "historical_avg"]
    assert avg is not None and avg > 10, f"average {avg} was pulled down by per-pound prices"


def test_an_item_with_no_like_basis_history_reports_no_history():
    hist = _turkey_history()
    hist["unit_price"] = 3.60          # every historical row is package-priced
    out = compute_historical_stats(_current("Canada Grade A Turkey", 2.19), hist)
    assert int(out.loc[0, "historical_count"]) == 0
    assert not bool(out.loc[0, "is_lowest_historical"])
