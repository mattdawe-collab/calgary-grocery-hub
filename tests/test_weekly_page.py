import json

import pandas as pd

from tools.weekly_page import build_page_model, render_weekly_page


def _df():
    return pd.DataFrame({
        "Store": ["Sobeys", "Sobeys", "Calgary Co-op", "Walmart"],
        "Item": ["Bacon 500 g", "Flat Cabbage", "Gala Apples", "Puffer Jacket"],
        "Price_Value": [5.99, 0.98, 1.69, 24.0],
        "display_category": ["Pork", "Produce", "Produce", "Other"],
        "deal_score": [88.0, 72.0, 100.0, 40.0],
        "historical_avg": [8.49, 1.37, 7.36, None],
        "pct_below_avg": [30.0, 28.0, 77.0, None],
        "historical_count": [12, 5, 18, 0],
        "is_lowest_historical": [False, False, True, False],
        "cross_store_rank": [1, None, 2, None],
        "cross_store_count": [4, 1, 3, 1],
        "action_label": ["Stock up", "Buy this week", "Stock up", "Skip"],
        "why_bullets": ["30% below avg $8.49; Cheapest of 4 stores", "28% below avg $1.37", "77% below avg $7.36; Lowest seen", ""],
        "Valid_From": ["2026-09-17"] * 4,
        "Valid_Until": ["2026-09-23"] * 3 + ["2026-10-21"],
        "confidence_score": [90, 60, 95, 10],
        "unit_price": [11.98, None, None, None],
        "unit_type": ["/kg", None, None, None],
    }, index=[10, 11, 12, 13])


def test_model_has_every_deal_and_store_summaries():
    model = build_page_model(_df(), latest=None, base_url="https://x.test/")
    assert len(model["deals"]) == 4                      # comprehensive: nothing dropped
    assert model["week_ending"] == "2026-09-23"          # modal date, not the Walmart outlier
    stores = {s["name"]: s for s in model["stores"]}
    assert stores["Sobeys"]["deal_count"] == 2
    assert model["stores"][0]["name"] in {"Sobeys", "Calgary Co-op"}   # sorted by strength
    assert model["top_deals"][0]["item"] == "Gala Apples"


def test_deal_rows_carry_evidence_and_history_link():
    model = build_page_model(_df(), latest=None, base_url="https://x.test/")
    bacon = next(d for d in model["deals"] if d["item"].startswith("Bacon"))
    assert bacon["url"] == "https://x.test/share/deals/10/"
    assert bacon["pct_below_avg"] == 30
    assert bacon["cross_store"] == "cheapest of 4 stores"
    assert "30% below avg $8.49" in bacon["why"]


def test_render_embeds_data_and_reports():
    latest = {"week_ending": "2026-09-23", "store_report": "STORE TEXT #YYCDeals", "category_report": "CAT TEXT #YYCDeals",
              "facebook_post": "FB TEXT", "generated_at": "2026-09-23T08:20:00"}
    model = build_page_model(_df(), latest=latest, base_url="https://x.test/")
    html = render_weekly_page(model)
    assert "<title>" in html and "Calgary" in html
    assert "https://x.test/share/deals/12/" in html
    assert "STORE TEXT" in html and "CAT TEXT" in html
    assert 'id="deal-data"' in html
    embedded = json.loads(html.split('id="deal-data"', 1)[1].split(">", 1)[1].split("</script>", 1)[0])
    assert embedded["total"] == 4
    assert "deals" not in embedded            # rows live in the DOM once, not twice
    assert "<script>alert" not in html


def test_render_escapes_item_names():
    df = _df()
    df.loc[10, "Item"] = "<script>alert(1)</script> Bacon"
    html = render_weekly_page(build_page_model(df, latest=None, base_url="https://x.test/"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_top_board_dedupes_same_item_across_sister_banners():
    # Sobeys and Safeway run one flyer, so this is one deal, not two.
    df = _df()
    df.loc[14] = df.loc[12]
    df.loc[14, "Store"] = "Safeway"
    df.loc[12, "Store"] = "Sobeys"
    model = build_page_model(df, latest=None, base_url="https://x.test/")
    names = [d["item"] for d in model["top_deals"]]
    assert names.count("Gala Apples") == 1


def test_top_board_keeps_the_same_item_at_a_competing_company():
    # Co-op and Safeway are different companies. Both are real choices and
    # collapsing them would hide the one nearer the shopper.
    df = _df()
    df.loc[14] = df.loc[12]                   # row 12 is Calgary Co-op
    df.loc[14, "Store"] = "Safeway"
    model = build_page_model(df, latest=None, base_url="https://x.test/")
    names = [d["item"] for d in model["top_deals"]]
    assert names.count("Gala Apples") == 2


def test_page_week_ending_matches_the_day_flyers_actually_expire():
    df = _df()
    df["Valid_Until"] = ["2026-09-30T23:59:59-04:00"] * len(df)
    df["Valid_From"] = ["2026-09-24T03:00:00-04:00"] * len(df)
    model = build_page_model(df, latest=None, base_url="https://x.test/")
    assert model["week_ending"] == "2026-09-30"
    assert model["valid_from"] == "2026-09-24"
