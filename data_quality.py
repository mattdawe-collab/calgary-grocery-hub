"""
Shared data-quality rules for Calgary Grocery Hub.

The scraper, dashboard API, and report generator all need the same answers for:
- whether an item belongs in a grocery-focused deal feed,
- which category should win when raw AI/statistical labels are noisy,
- whether a parsed unit price is plausible enough to use in scoring.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


UNKNOWN_CATEGORY = "Other"
VALID_CATEGORIES = {
    "Produce",
    "Beef",
    "Pork",
    "Poultry",
    "Lamb",
    "Seafood",
    "Dairy & Eggs",
    "Bakery",
    "Pantry",
    "Frozen",
    "Beverages",
    "Household & Personal",
    "Snacks",
    "Pet",
    "Prepared Foods",
    "General Merchandise",
    UNKNOWN_CATEGORY,
}


# Strong rules run before trusting an existing category. Keep these deliberately
# specific; broad terms belong in CATEGORY_RULES below.
STRONG_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "Pet",
        [
            "cat litter", "cat food", "dog food", "cat treat", "dog treat",
            "dog chew", "dog chews", "chew toy", "chew toys", "one paw",
            "whiskas", "purina", "cesar", "fancy feast", "temptations",
            "pedigree", "iams", "friskies",
        ],
    ),
    (
        "Household & Personal",
        [
            "nivea", "q-tips", "cotton swabs", "diaper", "diapers",
            "baby wipes", "pull-ups", "training pants", "detergent",
            "toilet paper", "bathroom tissue", "paper towel", "facial tissue",
            "garbage bags", "dish soap", "dish tabs", "shampoo", "conditioner",
            "body wash", "soap", "toothpaste", "deodorant", "tampons",
            "pads", "liners", "vitamin", "vitamins", "formula", "emulgel",
        ],
    ),
    (
        "Seafood",
        [
            "ahi tuna", "tuna steak", "salmon", "shrimp", "prawn", "prawns",
            "tilapia", "basa", "pollock", "cod", "halibut", "haddock",
            "sole", "trout", "snapper", "scallop", "scallops", "mussel",
            "mussels", "oyster", "oysters", "crab", "lobster", "lobsters",
        ],
    ),
    (
        "Snacks",
        [
            "potato chips", "tortilla chips", "kettle cooked", "doritos",
            "lay's", "lays", "twizzlers", "candy", "chocolate bar",
            "chocolate bars", "bagged chocolate", "popcorn", "pretzel",
            "pretzels", "gushers", "fruit by the foot", "granola bars",
            "protein bars", "seaweed snack",
        ],
    ),
    (
        "Pantry",
        [
            "refried beans", "baked beans", "canned beans", "pasta sauce",
            "tomato sauce", "granulated sugar", "brown sugar", "flour",
            "peanut butter", "mayonnaise", "mayo", "croutons", "seasoning",
            "seasonings", "rice", "pasta", "cereal", "broth", "soup",
            "canned", "noodles", "instant noodles", "cooking oil",
            "olive oil", "vegetable oil",
        ],
    ),
    (
        "Frozen",
        [
            "frozen entree", "frozen entree", "frozen pizza", "pizza pops",
            "ice cream", "gelato", "popsicle", "hash browns", "home fries",
            "perogies",
        ],
    ),
    (
        "Beverages",
        [
            "sparkling water", "flavoured water", "flavored water", "soda",
            "soft drink", "juice", "coffee", "tea", "gatorade", "powerade",
            "cold brew",
        ],
    ),
    (
        "Dairy & Eggs",
        [
            "cream cheese", "sour cream", "cheese", "yogurt", "yoghurt",
            "butter", "margarine", "eggs", "milk", "cottage cheese",
        ],
    ),
    (
        "Prepared Foods",
        [
            "rotisserie", "sushi", "meal kit", "taco kit", "ready meal", "loaded fries",
            "prepared", "deli tray", "entree", "entrees",
        ],
    ),
]


CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "Produce",
        [
            "apple", "apples", "banana", "bananas", "berry", "berries",
            "blueberry", "strawberry", "grape", "grapes", "orange",
            "oranges", "grapefruit", "mango", "mangoes", "kiwi", "plantain",
            "plantains", "plum", "plums", "peach", "peaches", "pear",
            "pears", "melon", "lettuce", "romaine", "salad", "salads", "tomato",
            "tomatoes", "cucumber", "cucumbers", "avocado", "avocados",
            "pepper", "peppers", "corn", "potato", "potatoes", "onion",
            "onions", "carrot", "carrots", "broccoli", "cauliflower",
            "mushroom", "mushrooms", "celery", "spinach", "asparagus",
            "dragon fruit", "pomelo", "garlic", "methi", "bean sprout",
            "bean sprouts", "okra", "guava", "vegetable", "vegetables",
            "fruit tray", "fruit trays", "pineapple", "lemon", "lemons",
            "lime", "limes", "watermelon",
        ],
    ),
    ("Seafood", ["salmon", "shrimp", "prawn", "fish", "tuna", "cod", "crab"]),
    ("Beef", ["beef", "steak", "sirloin", "ribeye", "tenderloin", "brisket", "prime rib"]),
    ("Pork", ["pork", "bacon", "ham", "wiener", "wieners", "sausage", "ribs", "pepperoni"]),
    ("Poultry", ["chicken", "turkey", "duck", "drumstick", "drumsticks"]),
    ("Lamb", ["lamb"]),
    ("Dairy & Eggs", ["milk", "cheese", "yogurt", "yoghurt", "butter", "cream", "egg", "eggs"]),
    (
        "Bakery",
        [
            "bread", "bagel", "bagels", "bun", "buns", "roll", "rolls",
            "tortilla", "tortillas", "naan", "pita", "muffin", "muffins",
            "croissant", "croissants", "danish", "biscuits", "pastries",
            "cake", "cakes", "donut", "donuts", "baguette", "baguettes",
            "cupcake", "cupcakes", "crepe", "crepes", "texas toast",
        ],
    ),
    (
        "Pantry",
        [
            "pasta", "sauce", "seasoning", "seasonings", "rice", "cereal",
            "soup", "broth", "oil", "flour", "sugar", "peanut butter",
            "jam", "honey", "marshmallow", "marshmallows", "pudding",
            "beans", "canned", "mayonnaise", "mayo", "dressing", "crouton",
            "croutons", "noodle", "noodles", "atta", "salt", "side dish",
            "chef boyardee", "spice tailor",
        ],
    ),
    ("Frozen", ["frozen", "ice cream", "gelato", "pizza", "popsicle", "hash browns", "home fries"]),
    ("Beverages", ["water", "sparkling", "soda", "pop", "juice", "coffee", "tea", "beverage", "drink", "drinks"]),
    (
        "Snacks",
        [
            "chip", "chips", "cracker", "crackers", "snack", "snacks",
            "cookie", "cookies", "chocolate", "candy", "popcorn", "granola",
            "pretzel", "pretzels",
        ],
    ),
    (
        "Household & Personal",
        [
            "pads", "liners", "tampons", "lotion", "q-tips", "cotton swabs",
            "baby wipes", "wipes", "diaper", "diapers", "dishwashing",
            "dish soap", "batteries", "garbage bags", "detergent",
            "toilet paper", "paper towel", "shampoo", "soap", "conditioner",
            "body wash", "facial tissue", "bathroom tissue", "dish tabs",
            "cleaner", "cleaners", "vitamin", "vitamins", "formula",
        ],
    ),
    ("Pet", ["cat food", "dog food", "cat treat", "dog treat", "cat litter"]),
    ("Prepared Foods", ["deli", "prepared", "entree", "entrees", "meatloaf", "rotisserie", "sushi", "meal kit"]),
]


FOOD_PROTECTION_TERMS = {
    term
    for category, terms in CATEGORY_RULES + STRONG_CATEGORY_RULES
    if category != "General Merchandise"
    for term in terms
}


NON_GROCERY_PATTERNS = [
    r"\b(?:smart\s*)?tv\b",
    r"\broku\b",
    r"\bairpods?\b",
    r"\b(?:bluetooth|wireless).*(?:speaker|headphones|earbuds)\b",
    r"\b(?:headphones?|earbuds?|speaker|monitor|camera|karaoke machine)\b",
    r"\b(?:samsung galaxy|iphone|smartphone|cell phone)\b",
    r"\b(?:electric|mountain|e-?)bike\b",
    r"\b(?:bicycle|scooter)\b",
    r"\b(?:kayak|paddle board|hot tub|air bed|mattress)\b",
    r"\b(?:sofa|loveseat|recliner|tv stand|patio set|outdoor chat set)\b",
    r"\b(?:zero gravity chairs?|office chair|director's chair)\b",
    r"\b(?:propane gas grill|pellet grill|griddle combo|tabletop griddle|griddle with hood|gas/griddle)\b",
    r"\b(?:lawn mower|cordless lawn|garden hose)\b",
    r"\b(?:lego|barbie|hot wheels|action figure|building set)\b",
    r"\btoy(?:s)?\b",
    r"\b(?:car seat|stroller|travel system|bassinet|bassine|breast pump)\b",
    r"\b(?:perfume|fashion bag|sunglasses|sandals|flip-flops?)\b",
    r"\b(?:t-shirt|shirt|shorts|helmet)\b",
    r"\b(?:motor oil|conventional motor|windshield washer|automotive)\b",
    r"\bblood pressure monitor\b",
]


UNIT_PRICE_LIMITS = {
    "$/kg": 250.0,
    "$/L": 500.0,
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).casefold().strip()


def _term_matches(text: str, term: str) -> bool:
    term = term.casefold().strip()
    if not term:
        return False
    if " " in term or "-" in term or "'" in term or "&" in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _any_term_matches(text: str, terms: list[str] | set[str]) -> bool:
    return any(_term_matches(text, term) for term in terms)


def normalize_category(category: Any) -> str:
    text = str(category or "").strip()
    if not text or text.casefold() == "nan":
        return UNKNOWN_CATEGORY
    return text if text in VALID_CATEGORIES else UNKNOWN_CATEGORY


def infer_category_from_name(item_name: Any, rules: list[tuple[str, list[str]]] | None = None) -> str | None:
    text = _clean_text(item_name)
    if not text:
        return None
    for category, terms in rules or CATEGORY_RULES:
        if _any_term_matches(text, terms):
            return category
    return None


def repair_category(item_name: Any, current_category: Any = None) -> tuple[str, str]:
    """Return a corrected category and source label.

    Source labels:
    - ai: existing category was trusted
    - corrected: strong name evidence overrode the existing category
    - inferred: category was inferred because the existing value was Other/blank
    - fallback: still uncategorized
    """
    current = normalize_category(current_category)
    strong = infer_category_from_name(item_name, STRONG_CATEGORY_RULES)
    if strong and strong != current:
        return strong, "corrected" if current != UNKNOWN_CATEGORY else "inferred"
    if current != UNKNOWN_CATEGORY:
        return current, "ai"
    inferred = infer_category_from_name(item_name, CATEGORY_RULES)
    if inferred:
        return inferred, "inferred"
    return UNKNOWN_CATEGORY, "fallback"


def is_non_grocery_item(item_name: Any) -> bool:
    text = _clean_text(item_name)
    if not text:
        return False

    # Keep foods, consumable household items, and pet staples even when a word
    # like "grilling" or "monitoring" appears in the name.
    if _any_term_matches(text, FOOD_PROTECTION_TERMS):
        return False

    return any(re.search(pattern, text) for pattern in NON_GROCERY_PATTERNS)


def append_quality_flag(existing: Any, flag: str) -> str:
    parts = [
        part.strip()
        for part in str(existing or "").split(";")
        if part and part.strip() and part.strip().casefold() != "nan"
    ]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)


def validate_unit_price(unit_price: Any, unit_type: Any) -> str | None:
    try:
        if pd.isna(unit_price):
            return None
        value = float(unit_price)
    except (TypeError, ValueError):
        return "unit_price_invalid"

    if value <= 0:
        return "unit_price_invalid"

    unit = str(unit_type or "").strip()
    limit = UNIT_PRICE_LIMITS.get(unit, 500.0)
    if value > limit:
        return "unit_price_outlier"
    return None


def mark_grocery_relevance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Item" not in df.columns:
        return df
    df = df.copy()
    df["is_grocery_relevant"] = ~df["Item"].apply(is_non_grocery_item)
    if "quality_flags" not in df.columns:
        df["quality_flags"] = ""
    mask = ~df["is_grocery_relevant"]
    if mask.any():
        df.loc[mask, "quality_flags"] = df.loc[mask, "quality_flags"].apply(
            lambda flags: append_quality_flag(flags, "non_grocery")
        )
    return df


def filter_grocery_relevant(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    marked = mark_grocery_relevance(df)
    if "is_grocery_relevant" not in marked.columns:
        return marked, marked.iloc[0:0].copy()
    excluded = marked[~marked["is_grocery_relevant"]].copy()
    kept = marked[marked["is_grocery_relevant"]].copy().reset_index(drop=True)
    return kept, excluded


def sanitize_unit_prices(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if df.empty or "unit_price" not in df.columns:
        return df, 0
    df = df.copy()
    if "quality_flags" not in df.columns:
        df["quality_flags"] = ""

    issues = df.apply(
        lambda row: validate_unit_price(row.get("unit_price"), row.get("unit_type")),
        axis=1,
    )
    mask = issues.notna()
    if not mask.any():
        return df, 0

    for issue in sorted(set(issues[mask])):
        issue_mask = issues == issue
        df.loc[issue_mask, "quality_flags"] = df.loc[issue_mask, "quality_flags"].apply(
            lambda flags, issue=issue: append_quality_flag(flags, issue)
        )

    df.loc[mask, "unit_price"] = pd.NA
    if "unit_type" in df.columns:
        df.loc[mask, "unit_type"] = pd.NA
    if "grams_equivalent" in df.columns:
        df.loc[mask, "grams_equivalent"] = pd.NA
    return df, int(mask.sum())


def add_quality_metadata(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = mark_grocery_relevance(df)
    if "quality_flags" not in df.columns:
        df["quality_flags"] = ""

    if "historical_count" in df.columns:
        hist = pd.to_numeric(df["historical_count"], errors="coerce").fillna(0)
        no_history = hist <= 0
        low_history = (hist > 0) & (hist < 3)
        df.loc[no_history, "quality_flags"] = df.loc[no_history, "quality_flags"].apply(
            lambda flags: append_quality_flag(flags, "no_history")
        )
        df.loc[low_history, "quality_flags"] = df.loc[low_history, "quality_flags"].apply(
            lambda flags: append_quality_flag(flags, "low_history")
        )

    if "ai_confidence" in df.columns:
        statistical = df["ai_confidence"].astype(str).str.casefold() == "statistical"
        df.loc[statistical, "quality_flags"] = df.loc[statistical, "quality_flags"].apply(
            lambda flags: append_quality_flag(flags, "statistical_scoring")
        )

    if "category_source" in df.columns:
        inferred = df["category_source"].astype(str).isin(["inferred", "corrected", "fallback"])
        df.loc[inferred, "quality_flags"] = df.loc[inferred, "quality_flags"].apply(
            lambda flags: append_quality_flag(flags, "category_review")
        )

    df["data_quality_score"] = df["quality_flags"].apply(_quality_score_from_flags)
    return df


def _quality_score_from_flags(flags: Any) -> int:
    penalties = {
        "non_grocery": 100,
        "unit_price_invalid": 35,
        "unit_price_outlier": 35,
        "no_history": 20,
        "low_history": 10,
        "statistical_scoring": 10,
        "category_review": 8,
    }
    score = 100
    for flag in str(flags or "").split(";"):
        score -= penalties.get(flag.strip(), 0)
    return max(0, min(100, score))
