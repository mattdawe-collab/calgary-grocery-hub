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


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def parse_dates(series: Any) -> pd.Series:
    """Parse a column of dates that mixes formats, without silently blanking rows.

    pandas 2.x infers a single format from the first non-null value; with
    errors="coerce" every other format then becomes NaT. The archive holds
    "2025-12-12 00:00:00", "2026-05-13" and ISO-8601 stamps with offsets side
    by side, and that inference blanked 26,827 Date cells between May and
    September 2026, silently shrinking the 180-day history window used for
    scoring. format="ISO8601" parses each value on its own terms.

    Timezone-aware values are converted to naive local days so comparisons
    against naive timestamps elsewhere keep working.
    """
    values = pd.Series(series)
    text = values.astype(str).str.strip()
    # Take the calendar day exactly as written. Converting an offset stamp to
    # UTC first can roll it to the next day (a 23:59:59-04:00 flyer end became
    # the following date), and these columns mean "which day", not an instant.
    leading_day = text.str.extract(r"^(\d{4}-\d{2}-\d{2})", expand=False)
    parsed = pd.to_datetime(leading_day, errors="coerce", format="%Y-%m-%d")
    rest = parsed.isna() & values.notna() & (text != "") & (text.str.lower() != "nan")
    if rest.any():
        fallback = pd.to_datetime(text[rest], errors="coerce", format="mixed")
        try:
            fallback = fallback.dt.tz_localize(None)
        except (AttributeError, TypeError):
            pass
        parsed.loc[rest] = fallback
    return parsed


def normalize_archive_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Rewrite Date / Valid_From / Valid_Until as plain YYYY-MM-DD strings.

    One canonical on-disk format means no future reader has to guess, and the
    file stops mixing "2026-05-13" with "2026-05-13T23:59:59-04:00".
    """
    out = df.copy()
    for column in ("Date", "Valid_From", "Valid_Until"):
        if column in out.columns:
            parsed = parse_dates(out[column])
            out[column] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna())
    return out


# ---------------------------------------------------------------------------
# How a meat price is quoted
# ---------------------------------------------------------------------------
# Flipp sends a bare number with no unit. "Frozen Turkey, price 2.99" is
# $2.99 per pound, but stored as a package price it looked like an 85%
# discount and pushed four fake turkey deals to the top of the protein list,
# while the one store that listed a real whole-bird price ranked last.
#
# We cannot recover the unit for every item, and guessing would trade one
# wrong answer for another. So we infer only where the physical size of the
# cut makes a package price impossible, and mark the rest "unknown" instead of
# pretending. What actually protects the scoring is never averaging one basis
# against another - see basis_is_comparable().

RAW_PROTEIN_CATEGORIES = ("Beef", "Pork", "Poultry", "Lamb", "Seafood")

BASIS_PER_LB = "per_lb"
BASIS_EACH = "each"
BASIS_UNKNOWN = "unknown"

# Cuts sold whole or in multi-pound pieces, with the highest price at which a
# package price is still physically implausible. A frozen turkey runs 4 kg and
# up, so even at the cheapest price per pound ever recorded it clears $10.
LARGE_CUT_PATTERNS = (
    (r"\bturkey" , 10.00),
    (r"\b(whole|frying|roasting)\s+chicken", 7.00),
    (r"\bchicken\b(?=.*\bwhole\b)", 7.00),
    (r"\b(pot|oven|rib|cross\s*rib|sirloin\s*tip|prime\s*rib|chuck|round)\s*roast", 8.00),
    (r"\broast\b", 8.00),
    (r"\bbrisket\b", 8.00),
    (r"\bleg\s+of\s+lamb\b", 8.00),
    (r"\b(pork\s+)?(shoulder|butt)\b", 8.00),
    (r"\bham\b(?=.*\b(whole|half|bone[- ]?in)\b)", 8.00),
    (r"\brack\s+of\b", 8.00),
)

# An explicit pack size means the number really is for that package.
_PACK_SIZE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:g|kg|ml|l|lb|lbs|oz)\b|\b\d+\s*(?:x|pk|pack|'s|s)\b",
    re.IGNORECASE,
)


def infer_price_basis(item_name, category, price_value, price_basis=None, unit_price=None) -> str:
    """Return how this price is quoted: per_lb, each, or unknown.

    Only rewrites a basis when a package price is physically impossible for
    the cut. Anything genuinely ambiguous comes back as "unknown" so callers
    can decline to compare it rather than invent a discount.
    """
    existing = _clean_text(price_basis)
    # Anything the parser already resolved (per_100g, per_lb, multi_buy) stands.
    if existing and existing not in ("each", "nan"):
        return str(price_basis)

    if unit_price is not None and not (isinstance(unit_price, float) and pd.isna(unit_price)):
        return BASIS_EACH

    if normalize_category(category) not in RAW_PROTEIN_CATEGORIES:
        return BASIS_EACH

    text = _clean_text(item_name)
    if not text:
        return BASIS_EACH

    try:
        price = float(price_value)
    except (TypeError, ValueError):
        return BASIS_UNKNOWN

    if _PACK_SIZE_RE.search(text):
        return BASIS_EACH

    for pattern, max_package_price in LARGE_CUT_PATTERNS:
        if re.search(pattern, text):
            # Below the threshold a package price is impossible, above it a
            # per-pound price is: nobody sells turkey at $24.99 a pound.
            return BASIS_PER_LB if 0 < price <= max_package_price else BASIS_EACH

    return BASIS_UNKNOWN


def basis_is_comparable(left, right) -> bool:
    """True when two prices are quoted the same way and may share an average.

    Averaging $2.19/lb turkey against a $35 whole bird produced the "85%
    below average" that made this worth fixing.
    """
    return _clean_text(left) == _clean_text(right)


def add_price_basis(df: pd.DataFrame, category_column: str | None = None) -> pd.DataFrame:
    """Add a resolved `basis` column to a deals or archive frame."""
    if df is None or len(df) == 0:
        out = df.copy() if df is not None else df
        if out is not None:
            out["basis"] = pd.Series(dtype=str)
        return out

    out = df.copy()
    if category_column is None:
        for candidate in ("display_category", "ai_category", "Category"):
            if candidate in out.columns:
                category_column = candidate
                break

    categories = out[category_column] if category_column in (out.columns if category_column else []) else pd.Series([None] * len(out), index=out.index)
    unit_prices = out["unit_price"] if "unit_price" in out.columns else pd.Series([None] * len(out), index=out.index)
    bases = out["price_basis"] if "price_basis" in out.columns else pd.Series([None] * len(out), index=out.index)

    out["basis"] = [
        infer_price_basis(item, cat, price, basis, unit)
        for item, cat, price, basis, unit in zip(
            out.get("Item", pd.Series([""] * len(out), index=out.index)),
            categories, out.get("Price_Value", pd.Series([0] * len(out), index=out.index)),
            bases, unit_prices,
        )
    ]
    return out


# ---------------------------------------------------------------------------
# Sister banners
# ---------------------------------------------------------------------------
# Sobeys and Safeway run the same flyer, as do Superstore and No Frills, so the
# same deal took two slots on a shortlist that only holds a handful.

PARENT_COMPANY = {
    "Sobeys": "Empire",
    "Safeway": "Empire",
    "FreshCo": "Empire",
    "Real Canadian Superstore": "Loblaw",
    "No Frills": "Loblaw",
    "Independent Grocer": "Loblaw",
    "Save-On-Foods": "Pattison",
    "Calgary Co-op": "Co-op",
    "Walmart": "Walmart",
}

STORE_SHORT_NAMES = {
    "Real Canadian Superstore": "Superstore",
    "Save-On-Foods": "Save-On",
    "Calgary Co-op": "Co-op",
}


def _short_store(name) -> str:
    name = str(name or "").strip()
    return STORE_SHORT_NAMES.get(name, name)


def dedupe_sister_banners(df: pd.DataFrame, name_column: str = "Item") -> pd.DataFrame:
    """Collapse the same product listed at banners of the same parent company.

    Keeps the cheapest listing and records the others in `also_at`, so the
    shopper still learns the deal is available at their nearer store.
    """
    if df is None or len(df) == 0 or "Store" not in df.columns:
        return df

    out = df.copy()
    parents = out["Store"].map(lambda s: PARENT_COMPANY.get(str(s).strip(), str(s).strip()))
    keys = out[name_column].astype(str).str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    group = parents + "|" + keys

    price = pd.to_numeric(out.get("Price_Value"), errors="coerce")
    score = pd.to_numeric(out.get("deal_score"), errors="coerce").fillna(0)
    order = pd.DataFrame({"g": group, "p": price.fillna(price.max()), "s": -score})

    keep_index = order.sort_values(["g", "p", "s"]).groupby("g", sort=False).head(1).index
    also = {}
    for g, rows in out.groupby(group, sort=False):
        if len(rows) > 1:
            kept = order.loc[rows.index].sort_values(["p", "s"]).index[0]
            others = [_short_store(s) for i, s in rows["Store"].items() if i != kept]
            also[kept] = ", ".join(dict.fromkeys(others))

    out = out.loc[keep_index].copy()
    out["also_at"] = [also.get(i, "") for i in out.index]
    return out.sort_index()


def brand_aware_name(item_name, brand) -> str:
    """Prefix the brand when the item name omits it.

    Flipp returns name and brand as separate fields and the scraper only kept
    the name, so every store's generic "Frozen Turkey" shared one price
    history regardless of whose bird it was.
    """
    name = str(item_name or "").strip()
    brand_text = str(brand or "").strip()
    if not brand_text or brand_text.lower() in {"nan", "none", "null"}:
        return name
    if not name:
        return brand_text
    if brand_text.lower() in name.lower():
        return name
    return f"{brand_text} {name}"
