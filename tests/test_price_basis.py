import pandas as pd
import pytest

from data_quality import (
    PARENT_COMPANY,
    basis_is_comparable,
    dedupe_sister_banners,
    infer_price_basis,
)


# ---------------------------------------------------------------------------
# Inferring how a meat price is quoted
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "item,price",
    [
        ("Raised Without Antibiotics Frozen Grade A Turkeys", 2.19),
        ("Fresh Raised Without Antibiotics Grade A Turkeys", 2.77),
        ("Canada Grade A Turkey", 1.74),
        ("Frozen Turkey", 2.99),
        ("Whole Frying Chicken", 2.49),
        ("Fresh Boneless Cross Rib Pot Roast", 4.99),
        ("Beef Brisket", 5.99),
    ],
)
def test_large_cuts_priced_low_are_per_pound(item, price):
    # A whole turkey cannot cost $2.19. These are per-pound prices that Flipp
    # sends with no unit, and treating them as package prices is what put four
    # fake turkey deals at the top of the protein list.
    assert infer_price_basis(item, "Poultry", price, "each", None) == "per_lb"


@pytest.mark.parametrize(
    "item,price,unit_price",
    [
        ("UTILITY GRADE FROZEN TURKEYS, 3-5 KG", 18.00, 3.60),
        ("WATSON RIDGE CHICKEN BREASTS, 800 G", 13.00, 16.25),
    ],
)
def test_items_carrying_a_weight_or_unit_price_stay_package_priced(item, price, unit_price):
    assert infer_price_basis(item, "Poultry", price, "each", unit_price) == "each"


def test_a_large_cut_at_a_plausible_package_price_is_not_guessed():
    # $24.99 for a whole turkey is a real package price; do not rewrite it.
    assert infer_price_basis("Frozen Turkey", "Poultry", 24.99, "each", None) == "each"


def test_ambiguous_cuts_are_marked_unknown_rather_than_guessed():
    # Bacon at $2.99 could be a 375g pack or a per-pound price. Say so.
    assert infer_price_basis("Bacon", "Pork", 2.99, "each", None) == "unknown"
    assert infer_price_basis("Chicken Wings", "Poultry", 4.99, "each", None) == "unknown"


def test_non_meat_is_left_alone():
    assert infer_price_basis("Gala Apples", "Produce", 0.99, "each", None) == "each"


def test_existing_per_100g_basis_is_never_overridden():
    assert infer_price_basis("Atlantic Salmon", "Seafood", 3.29, "per_100g", 32.90) == "per_100g"


# ---------------------------------------------------------------------------
# Keeping unlike prices out of the same average
# ---------------------------------------------------------------------------
def test_only_like_bases_are_compared():
    assert basis_is_comparable("per_lb", "per_lb") is True
    assert basis_is_comparable("each", "each") is True
    assert basis_is_comparable("unknown", "unknown") is True
    # The turkey bug: a $2.19/lb price averaged against a $35 whole bird.
    assert basis_is_comparable("per_lb", "each") is False
    assert basis_is_comparable("each", "per_100g") is False
    assert basis_is_comparable("unknown", "per_lb") is False


# ---------------------------------------------------------------------------
# Sister banners
# ---------------------------------------------------------------------------
def test_parent_company_groups_the_banners_that_share_flyers():
    assert PARENT_COMPANY["Sobeys"] == PARENT_COMPANY["Safeway"]
    assert PARENT_COMPANY["Real Canadian Superstore"] == PARENT_COMPANY["No Frills"]
    assert PARENT_COMPANY["Sobeys"] != PARENT_COMPANY["No Frills"]


def test_dedupe_collapses_the_same_deal_across_sister_banners():
    df = pd.DataFrame({
        "Store": ["Sobeys", "Safeway", "Calgary Co-op"],
        "Item": ["Bacon", "Bacon", "Bacon"],
        "Price_Value": [2.99, 2.99, 2.99],
        "deal_score": [100.0, 100.0, 95.0],
    })
    out = dedupe_sister_banners(df)
    assert len(out) == 2                                  # Co-op is a real alternative
    row = out[out.Store.str.contains("Sobeys")].iloc[0]
    assert "Safeway" in row["also_at"]                    # the other banner is still named


def test_dedupe_keeps_genuinely_different_prices():
    df = pd.DataFrame({
        "Store": ["Real Canadian Superstore", "No Frills"],
        "Item": ["WATSON RIDGE CHICKEN BREASTS, 800 G"] * 2,
        "Price_Value": [14.00, 13.00],
        "deal_score": [90.0, 100.0],
    })
    out = dedupe_sister_banners(df)
    assert len(out) == 1                       # same product, same company
    assert out.iloc[0]["Price_Value"] == 13.00  # keeps the cheaper one
    assert "Superstore" in out.iloc[0]["also_at"]


def test_dedupe_is_a_no_op_without_sister_banners():
    df = pd.DataFrame({
        "Store": ["Sobeys", "Calgary Co-op", "Walmart"],
        "Item": ["Bacon", "Ham", "Eggs"],
        "Price_Value": [2.99, 3.99, 4.99],
        "deal_score": [90.0, 80.0, 70.0],
    })
    assert len(dedupe_sister_banners(df)) == 3
