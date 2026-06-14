import pandas as pd

from send_telegram_digest import _category_group_mask, _filter_deals


def _base_rows():
    return [
        {
            "Item": "Breaded Chicken Breasts",
            "Store": "A",
            "Price_Value": 8.99,
            "display_category": "Poultry",
            "deal_score": 100,
            "action_label": "Stock up",
        },
        {
            "Item": "Fresh Air-Chilled Chicken Breast",
            "Store": "B",
            "Price_Value": 5.99,
            "display_category": "Poultry",
            "deal_score": 82,
            "action_label": "Buy this week",
        },
        {
            "Item": "Romaine Lettuce",
            "Store": "C",
            "Price_Value": 1.99,
            "display_category": "Produce",
            "deal_score": 90,
            "action_label": "Stock up",
        },
        {
            "Item": "Caramelized Onion Hummus",
            "Store": "C",
            "Price_Value": 3.49,
            "display_category": "Produce",
            "deal_score": 88,
            "action_label": "Buy this week",
        },
        {
            "Item": "Ataulfo Mangoes",
            "Store": "C",
            "Price_Value": 0.99,
            "display_category": "Produce",
            "deal_score": 90,
            "action_label": "Stock up",
        },
        {
            "Item": "Pasta Sauce",
            "Store": "D",
            "Price_Value": 2.99,
            "display_category": "Pantry",
            "deal_score": 95,
            "action_label": "Stock up",
        },
        {
            "Item": "Neo size 5 soccer ball",
            "Store": "E",
            "Price_Value": 15.99,
            "display_category": "Other",
            "deal_score": 99,
            "action_label": "Stock up",
        },
    ]


def test_protein_group_prioritizes_raw_chicken_breast_before_prepared():
    df = pd.DataFrame(_base_rows())

    filtered = _filter_deals(df, min_score=0, store=None, category=None, category_group="proteins")

    assert filtered["Item"].tolist() == [
        "Fresh Air-Chilled Chicken Breast",
        "Breaded Chicken Breasts",
    ]


def test_vegetable_group_includes_vegetable_produce_not_fruit():
    df = pd.DataFrame(_base_rows())
    mask = _category_group_mask(df, "vegetables", "display_category")

    assert df.loc[mask, "Item"].tolist() == ["Romaine Lettuce"]


def test_pantry_others_excludes_proteins_vegetables_and_non_food_other():
    df = pd.DataFrame(_base_rows())
    mask = _category_group_mask(df, "pantry_others", "display_category")

    assert df.loc[mask, "Item"].tolist() == ["Caramelized Onion Hummus", "Ataulfo Mangoes", "Pasta Sauce"]
