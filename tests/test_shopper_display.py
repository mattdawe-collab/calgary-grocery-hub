import pandas as pd

from tools.weekly_page import build_page_model, render_weekly_page


def _row(**kw):
    base = {
        "Store": "Sobeys", "Item": "Canada Grade A Turkey", "Price_Value": 2.19,
        "display_category": "Poultry", "deal_score": 90.0, "historical_avg": 2.60,
        "pct_below_avg": 16.0, "historical_count": 12, "is_lowest_historical": False,
        "cross_store_rank": 1, "cross_store_count": 2, "action_label": "Stock up",
        "why_bullets": "16% below avg", "Valid_From": "2026-10-01",
        "Valid_Until": "2026-10-07", "confidence_score": 80,
        "unit_price": None, "unit_type": None, "price_basis": "each",
    }
    base.update(kw)
    return base


def test_per_pound_meat_is_labelled_per_pound():
    # "$2.19" next to a "$18.00" whole turkey is unreadable. Say which is which.
    model = build_page_model(pd.DataFrame([_row()], index=[1]), None, "https://x.test/")
    deal = model["deals"][0]
    assert deal["basis"] == "per_lb"
    assert deal["price_label"] == "$2.19/lb"


def test_package_priced_meat_is_not_given_a_fake_unit():
    row = _row(Item="UTILITY GRADE FROZEN TURKEYS, 3-5 KG", Price_Value=18.0,
               unit_price=3.60, unit_type="$/kg")
    model = build_page_model(pd.DataFrame([row], index=[1]), None, "https://x.test/")
    deal = model["deals"][0]
    assert deal["basis"] == "each"
    assert deal["price_label"] == "$18.00"


def test_ambiguous_meat_is_flagged_as_not_comparable():
    row = _row(Item="Bacon", display_category="Pork", Price_Value=2.99)
    model = build_page_model(pd.DataFrame([row], index=[1]), None, "https://x.test/")
    assert model["deals"][0]["basis"] == "unknown"


def test_per_pound_label_reaches_the_rendered_page():
    model = build_page_model(pd.DataFrame([_row()], index=[1]), None, "https://x.test/")
    html = render_weekly_page(model)
    assert "$2.19/lb" in html
