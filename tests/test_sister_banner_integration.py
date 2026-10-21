import pandas as pd

from tools.weekly_page import build_page_model


def _sister_deals():
    rows = []
    for store, price, score in [
        ("Sobeys", 2.99, 100.0), ("Safeway", 2.99, 100.0),          # same company
        ("Real Canadian Superstore", 14.00, 90.0), ("No Frills", 13.00, 100.0),
        ("Calgary Co-op", 3.49, 95.0),                               # genuine alternative
    ]:
        rows.append({
            "Store": store, "Item": "Bacon" if price < 5 else "Chicken Breasts",
            "Price_Value": price, "display_category": "Pork" if price < 5 else "Poultry",
            "deal_score": score, "historical_avg": 6.85, "pct_below_avg": 50.0,
            "historical_count": 20, "is_lowest_historical": False,
            "cross_store_rank": 1, "cross_store_count": 2, "action_label": "Stock up",
            "why_bullets": "50% below avg", "Valid_From": "2026-10-01",
            "Valid_Until": "2026-10-07", "confidence_score": 80,
            "unit_price": None, "unit_type": None,
        })
    return pd.DataFrame(rows, index=range(10, 15))


def test_top_board_shows_one_row_per_deal_not_per_banner():
    model = build_page_model(_sister_deals(), latest=None, base_url="https://x.test/")
    board = model["top_deals"]
    stores = [d["store_short"] for d in board]
    assert not ("Sobeys" in stores and "Safeway" in stores), "same Empire deal listed twice"
    assert not ("Superstore" in stores and "No Frills" in stores), "same Loblaw deal listed twice"
    assert "Co-op" in stores, "a genuinely different store was dropped"


def test_top_board_names_the_sister_banner_so_shoppers_can_still_use_it():
    model = build_page_model(_sister_deals(), latest=None, base_url="https://x.test/")
    bacon = next(d for d in model["top_deals"] if d["item"] == "Bacon")
    assert "Safeway" in bacon["also_at"] or "Sobeys" in bacon["also_at"]


def test_top_board_keeps_the_cheaper_of_two_sister_prices():
    model = build_page_model(_sister_deals(), latest=None, base_url="https://x.test/")
    chicken = next(d for d in model["top_deals"] if d["item"] == "Chicken Breasts")
    assert chicken["price"] == 13.00
    assert chicken["store_short"] == "No Frills"


def test_store_cards_still_list_every_banner():
    # Deduping the shortlist must not hide a deal from the store you shop at.
    model = build_page_model(_sister_deals(), latest=None, base_url="https://x.test/")
    assert len(model["deals"]) == 5
    assert {s["short"] for s in model["stores"]} >= {"Sobeys", "Safeway", "No Frills"}


def test_also_at_never_names_the_store_it_is_already_on():
    # Two listings of one product at the same store collapse too, but the
    # note must not read "No Frills (+No Frills)".
    rows = []
    for price in (3.00, 3.50):
        rows.append({
            "Store": "No Frills", "Item": "NO NAME HONEY, 1 kg", "Price_Value": price,
            "display_category": "Pantry", "deal_score": 95.0, "historical_avg": 6.0,
            "pct_below_avg": 50.0, "historical_count": 10, "is_lowest_historical": False,
            "cross_store_rank": 1, "cross_store_count": 1, "action_label": "Stock up",
            "why_bullets": "50% below avg", "Valid_From": "2026-10-01",
            "Valid_Until": "2026-10-07", "confidence_score": 80,
            "unit_price": None, "unit_type": None,
        })
    model = build_page_model(pd.DataFrame(rows, index=[20, 21]), None, "https://x.test/")
    honey = next(d for d in model["top_deals"] if "HONEY" in d["item"])
    assert honey["also_at"] == ""
