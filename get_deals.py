"""
Calgary Grocery Hub - Deal Scraper v3.1

Updates:
- v3.1: Per-100g pricing fix:
    * Detects Sobeys/Safeway/Co-op fresh counter items priced per 100g
    * Converts price_basis to 'per_100g', sets unit_price to $/kg
    * Retroactively cleans historical archive per-100g entries
    * Adds per_100g_corrected flag for report generator
    * Anomaly detection safety net for unknown per-100g items
- v3.0: Major overhaul:
    * extract_price_data() now returns price_basis (per_lb, per_kg, multi_buy, each)
    * extract_unit_price() uses price_text and price_basis for much better coverage
    * Dedup immediately after extraction (before AI/scoring)
    * compute_historical_stats() uses ai_normalized_name + unit_price when available
    * compute_cross_store_stats() uses ai_normalized_name + unit_price when available
    * compute_statistical_score() rewritten: base 40, allows sub-50, no double-counting
    * Unified deal_score column (deterministic, replaces AI score as primary)
    * save_to_archive() saves price_basis, unit_price, unit_type for future comparisons
- v2.6: Fixed "0 deals" bug. Multi-key price lookup.
- v2.5: Restored API endpoints.
"""

import requests
import pandas as pd
import numpy as np
import datetime
from datetime import timedelta
import os
import time
import re
from dotenv import load_dotenv

# Optional: scipy for percentile calculations
try:
    from scipy.stats import percentileofscore
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Import AI analyzer (graceful fallback)
try:
    from ai_quality_analyzer import add_ai_analysis_to_dataframe
    AI_ANALYZER_AVAILABLE = True
except ImportError:
    AI_ANALYZER_AVAILABLE = False
    add_ai_analysis_to_dataframe = None

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path, override=True)

# Files
HISTORICAL_ARCHIVE = 'historical_archive.csv'
CURRENT_FLYERS = 'current_flyers.csv'

# Scraper Settings
POSTAL_CODE = os.getenv("POSTAL_CODE", "T3M1M9")

# PROVEN API CONSTANTS
BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

# Target stores
TARGET_STORES = [
    'Real Canadian Superstore',
    'No Frills',
    'Save-On-Foods',
    'Calgary Co-op',
    'Sobeys',
    'Safeway',
    'Walmart',
]

# Key Value Items to track
KEY_VALUE_ITEMS = [
    'milk', 'bread', 'eggs', 'butter', 'cheese', 'chicken breast',
    'ground beef', 'bacon', 'rice', 'pasta', 'cereal', 'yogurt',
    'orange juice', 'coffee', 'sugar', 'flour', 'cooking oil',
    'bananas', 'apples', 'potatoes', 'onions', 'tomatoes', 'lettuce'
]

# Item-level exclusion: filter out non-grocery items even if they appear in a grocery flyer
# Words that indicate alcohol (but NOT "non-alcoholic" or "de-alcoholized")
ALCOHOL_KEYWORDS = [
    'vodka', 'rum', 'whisky', 'whiskey', 'gin', 'tequila', 'cognac', 'brandy',
    'bourbon', 'scotch', 'mezcal', 'absinthe', 'vermouth', 'schnapps', 'sake',
    'merlot', 'cabernet', 'chardonnay', 'sauvignon blanc', 'pinot noir',
    'pinot grigio', 'riesling', 'malbec', 'shiraz', 'syrah', 'zinfandel',
    'prosecco', 'champagne', 'cava', 'moscato',
    'smirnoff', 'absolut', 'grey goose', 'bacardi', 'captain morgan',
    'jack daniels', 'crown royal', 'johnnie walker', 'hennessy', 'baileys',
    'jagermeister', 'kahlua', 'malibu', 'fireball',
    'white claw', 'truly hard', 'twisted tea', 'palm bay',
    'craft beer', 'lager', 'pilsner', 'stout', 'porter', 'pale ale', 'ipa',
]

# Full-phrase patterns that identify alcohol (matched as substrings)
ALCOHOL_PHRASES = [
    'wine bottle', 'red wine', 'white wine', 'rose wine', 'rosé wine',
    'sparkling wine', 'table wine',
    'beer case', 'beer pack', 'tall can',
    'rtd cocktail', 'hard lemonade', 'hard soda',
    'cooler pack', 'spirit mix',
]

# Non-alcoholic items that should NOT be excluded (whitelist patterns)
ALCOHOL_WHITELIST = [
    'non-alcoholic', 'non alcoholic', 'de-alcoholized', 'dealcoholized',
    'alcohol-free', 'alcohol free', '0%', 'zero alcohol', 'na beer',
    'wine vinegar', 'wine sauce', 'cooking wine',
]


def is_alcohol_item(item_name):
    """
    Check if an item is an alcoholic beverage.
    Returns True if the item should be excluded.
    Allows non-alcoholic versions through via whitelist.
    """
    import re as _re
    name_lower = item_name.lower()

    # Check whitelist first - if it matches, it's NOT alcohol
    for safe in ALCOHOL_WHITELIST:
        if safe in name_lower:
            return False

    # Check keywords with word boundary matching to avoid false positives
    # (e.g., "gin" matching "ginger", "rum" matching "spectrum", "ale" matching "sale")
    for kw in ALCOHOL_KEYWORDS:
        pattern = r'\b' + _re.escape(kw) + r'\b'
        if _re.search(pattern, name_lower):
            return True

    # Check phrases (these are long enough that substring is fine)
    for phrase in ALCOHOL_PHRASES:
        if phrase in name_lower:
            return True

    return False


# =============================================================================
# PER-100G DETECTION (v3.1)
# =============================================================================
# Sobeys/Safeway/Co-op price fresh meat counter items per 100g.
# The API returns bare numbers (e.g. "2.39") without the "/100g" unit.
# This causes these items to appear 70-80% cheaper than reality,
# poisoning deal scores, cross-store comparisons, and historical averages.

PER_100G_STORES = {'Sobeys', 'Safeway', 'Calgary Co-op', 'Save-On-Foods'}

# Fresh counter seafood/meat patterns that are per 100g at these stores.
# These match generic counter items (no brand, no package weight).
# Format: (regex_pattern, max_reasonable_per100g_price)
# The max price prevents false positives on per-package items with similar names.
PER_100G_ITEM_PATTERNS = [
    # --- Fresh counter seafood (generic names = per 100g) ---
    (r'(?:fresh\s+)?atlantic\s+salmon\s+(?:fillet|roast|portion|steak)', 8.0),
    (r'^atlantic\s+salmon$', 8.0),  # bare "Atlantic Salmon" (Save-On style)
    (r'(?:fresh\s+)?marinated\s+(?:atlantic\s+)?salmon\s+fillet', 8.0),
    (r'marinated\s+fresh\s+atlantic\s+salmon', 8.0),
    (r'(?:fresh\s+)?(?:wild\s+)?(?:pacific\s+)?cod\s+fillet', 8.0),
    (r'^cod\s+fillets?$', 8.0),
    (r'(?:fresh\s+)?(?:wild\s+)?halibut(?:\s+fillet|\s+steak)?', 15.0),
    (r'(?:fresh\s+)?steelhead\s+trout(?:\s+fillet)?', 8.0),
    (r'(?:fresh\s+)?(?:whole\s+)?rainbow\s+trout', 8.0),
    (r'^trout\s+fillets?$', 8.0),
    (r'(?:fresh\s+)?(?:wild\s+)?(?:pacific\s+)?sole\s+fillet', 8.0),
    (r'(?:fresh\s+)?(?:wild\s+)?tilapia\s+fillet', 6.0),
    (r'(?:fresh\s+)?haddock\s+fillet', 8.0),
    (r'(?:fresh\s+)?swordfish', 12.0),
    (r'(?:fresh\s+)?mahi\s+mahi', 10.0),
    (r'(?:wild\s+)?yellowfin\s+tuna\s+steak', 10.0),
    (r'coho\s+salmon\s+fillet', 8.0),
    (r'(?:wild\s+)?sockeye\s+salmon\s+fillet', 8.0),
    (r'chinook\s+(?:red\s+spring\s+)?salmon\s+fillet', 8.0),
    (r'red\s+spring\s+salmon\s+fillet', 8.0),
    # --- Fresh chicken counter items (bare names = per 100g) ---
    # Tight price ceiling ($5) to avoid false positives on per-package chicken wings
    (r'^chicken\s+wings?$', 5.0),
    (r'^chicken\s+wings?\s*,', 5.0),
    (r'^(?:glazed|marinated)\s+chicken\s+wings?$', 5.0),
]

# Patterns that EXCLUDE an item from per-100g detection.
# Branded, frozen, pre-packaged, or prepared items are per-package or per-lb.
PER_100G_EXCLUSION_BRANDS = [
    'compliments', 'maple leaf', 'schneiders', 'janes', 'high liner',
    'seaquest', 'sea quest', 'panache', 'cardinal', 'pinty',
    'belmont', 'great value', 'no name', 'pc ', 'kelseys',
    'impossible', 'marcangelo', 'johnsonville', 'sufra',
    'country classics', 'western family', 'hayter', 'clover leaf',
    'betty crocker', 'ultra natural', 'true north',
]

PER_100G_EXCLUSION_TERMS = [
    'frozen', 'breaded', 'battered', 'cooked', 'smoked', 'cured', 'canned',
    'nugget', 'strip', 'tender', 'bite', 'burger', 'sausage', 'cake',
    'pot pie', 'entrée', 'entree', 'ready to', 'in-store',
    'schnitzel', 'meatball', 'pepperette', 'kolbassa',
    'air-chilled', 'air chilled', 'helper', 'cheese ball',
    'crusted', 'flavoured', 'popcorn', 'imitation',
]

# Regex for explicit package weight (means it's per-package, not per-100g).
# v3.2: require >=2 digits or a decimal so "5g sodium" inside ingredient
# blurbs doesn't trip the detector. Real package weights are essentially
# always >=10g, >=100g, or fractional kg/lb.
_PER_100G_WEIGHT_RE = re.compile(r'(?:\d{2,}|\d*\.\d+)\s*(?:g|kg|lb|lbs|oz)\b')


def is_likely_per_100g(store, item_name, price_value, price_basis):
    """
    Detect if an item is likely priced per 100g but recorded as 'each'.

    Targets fresh meat/seafood counter items at Sobeys/Safeway/Co-op
    where the API returns a per-100g price without the unit indicator.

    Returns True if the item should be treated as per-100g.
    """
    if store not in PER_100G_STORES:
        return False

    # Only fix items currently marked as 'each' (per-100g wasn't detected by parser)
    if price_basis and price_basis not in ('each', '', None):
        return False

    item_lower = item_name.lower().strip()

    # Check exclusion brands (fast exit for branded products)
    for brand in PER_100G_EXCLUSION_BRANDS:
        if brand in item_lower:
            return False

    # Check exclusion terms (frozen, prepared, etc.)
    for term in PER_100G_EXCLUSION_TERMS:
        if term in item_lower:
            return False

    # Check for explicit weight in name (packaged product)
    if _PER_100G_WEIGHT_RE.search(item_lower):
        return False

    # Check if item matches known per-100g patterns
    for pattern, max_price in PER_100G_ITEM_PATTERNS:
        if re.search(pattern, item_lower):
            # Price sanity: must be in the per-100g range for this item type
            if price_value and 0.30 <= price_value <= max_price:
                return True

    return False


def apply_per_100g_corrections(df):
    """
    Detect and correct per-100g items in the dataframe.

    For detected items:
    - Sets price_basis to 'per_100g'
    - Computes unit_price as $/kg (price * 10)
    - Sets unit_type to '$/kg'
    - Adds per_100g_corrected flag

    Returns the corrected dataframe.
    """
    df['per_100g_corrected'] = False

    mask = df.apply(
        lambda row: is_likely_per_100g(
            row.get('Store', ''),
            row.get('Item', ''),
            row.get('Price_Value', 0),
            row.get('price_basis', '')
        ),
        axis=1
    )

    if mask.any():
        df.loc[mask, 'price_basis'] = 'per_100g'
        df.loc[mask, 'unit_price'] = (df.loc[mask, 'Price_Value'] * 10).round(2)
        df.loc[mask, 'unit_type'] = '$/kg'
        df.loc[mask, 'per_100g_corrected'] = True

        corrected_items = df.loc[mask, ['Store', 'Item', 'Price_Value']].values.tolist()
        print(f"   💲 Corrected {mask.sum()} per-100g items:")
        for store, item, price in corrected_items:
            real_per_kg = price * 10
            real_per_lb = real_per_kg * 0.453592
            print(f"      {store}: {item[:40]} ${price:.2f}/100g → ${real_per_kg:.2f}/kg (${real_per_lb:.2f}/lb)")

    return df


def _atomic_write_csv(df, path):
    """Write CSV atomically: tempfile + os.replace, with row-count sanity check.

    A direct df.to_csv() can corrupt the destination on power loss / OneDrive
    sync interruption / SMB hiccup. We write to a sibling tempfile and rename
    only on success. Raises if the row count looks wrong (defensive).
    """
    import tempfile
    if df is None or len(df) == 0:
        # Refuse to write an empty dataframe over a non-empty file
        if os.path.exists(path) and os.stat(path).st_size > 0:
            raise ValueError(
                f"Refusing to overwrite {path} with an empty dataframe (would lose data)"
            )
    dirpath = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(suffix='.csv', prefix='._archive_', dir=dirpath)
    try:
        os.close(fd)
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass
        raise


def clean_archive_per_100g(df_history, save_to_disk=True):
    """
    Retroactively detect and tag per-100g entries in the historical archive.

    This prevents contaminated per-100g prices from poisoning historical
    averages and cross-store comparisons.

    Args:
        df_history: archive DataFrame
        save_to_disk: if True (default) write back to HISTORICAL_ARCHIVE atomically.
                      Set to False when the caller (e.g. weekly_report_generator)
                      only needs the cleaned dataframe in memory.

    Returns the cleaned archive.
    """
    if df_history is None or len(df_history) == 0:
        return df_history

    rows_before = len(df_history)

    # Ensure columns exist
    if 'price_basis' not in df_history.columns:
        df_history['price_basis'] = None
    if 'unit_price' not in df_history.columns:
        df_history['unit_price'] = None
    if 'unit_type' not in df_history.columns:
        df_history['unit_type'] = None

    corrected = 0
    for idx, row in df_history.iterrows():
        # Skip entries already tagged
        current_basis = row.get('price_basis', '')
        if pd.notna(current_basis) and current_basis == 'per_100g':
            continue

        store = str(row.get('Store', ''))
        item = str(row.get('Item', ''))
        price = row.get('Price_Value', 0)
        if pd.isna(price):
            price = 0

        basis = str(current_basis) if pd.notna(current_basis) else ''

        if is_likely_per_100g(store, item, float(price), basis):
            df_history.at[idx, 'price_basis'] = 'per_100g'
            df_history.at[idx, 'unit_price'] = round(float(price) * 10, 2)
            df_history.at[idx, 'unit_type'] = '$/kg'
            corrected += 1

    if corrected > 0:
        print(f"   🔧 Retroactively tagged {corrected} historical per-100g entries")
        if save_to_disk:
            # Sanity check: this function only mutates cells, never adds/removes rows.
            assert len(df_history) == rows_before, (
                f"clean_archive_per_100g unexpectedly changed row count "
                f"({rows_before} -> {len(df_history)}); refusing to save"
            )
            _atomic_write_csv(df_history, HISTORICAL_ARCHIVE)

    return df_history


# =============================================================================
# FLIPP API FUNCTIONS (unchanged from v2.6)
# =============================================================================

def _request_with_retry(url, *, params=None, max_attempts=3, label='Flipp'):
    """GET with bounded retries + exponential backoff. Returns parsed JSON or None.

    A transient blip from Flipp on one of seven stores used to silently empty
    that store's section of the report. Three attempts with 2s/4s backoff
    catches the typical 502/timeouts we've seen.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                backoff = 2 ** attempt  # 2s, 4s
                print(f"   ⚠️ {label} attempt {attempt}/{max_attempts} failed ({e}); retrying in {backoff}s")
                time.sleep(backoff)
    print(f"   ❌ {label} gave up after {max_attempts} attempts: {last_err}")
    return None


def get_flipp_flyers(postal_code):
    """Fetch available flyers from Flipp API."""
    url = f"{BASE_URL}/flyers"
    params = {'postal_code': postal_code, 'locale': 'en-ca'}
    data = _request_with_retry(url, params=params, label='Flipp /flyers')
    if data is None:
        return []
    return data.get('flyers', [])


def get_flyer_items(flyer_id, merchant_name):
    """Fetch items from a specific flyer."""
    url = f"{BASE_URL}/flyers/{flyer_id}"
    data = _request_with_retry(url, label=f'Flipp /flyers/{flyer_id} ({merchant_name})')
    if data is None:
        return []

    # Proven logic: check items OR spread_items
    items = data.get('items') or data.get('spread_items') or []

    if len(items) == 0:
        print(f"   ⚠️ [DEBUG] {merchant_name} returned 0 items. Keys found: {list(data.keys())}")

    return items


def select_best_flyers(flyers, target_stores):
    """Select the newest GROCERY flyer for each target store."""
    selected = {}

    # Exclude non-grocery flyers
    exclusion_terms = ['liquor', 'wine', 'beer', 'spirits', 'alcohol', 'optical', 'pharmacy']

    for flyer in flyers:
        merchant = flyer.get('merchant', '')
        flyer_name = flyer.get('name', '').lower()
        merchant_lower = merchant.lower()

        # Check exclusion terms
        if any(term in flyer_name for term in exclusion_terms) or \
           any(term in merchant_lower for term in exclusion_terms):
            continue

        # Check if this merchant matches any target store
        for target in target_stores:
            if target.lower() in merchant_lower or merchant_lower in target.lower():
                valid_from = flyer.get('valid_from', '')

                # Keep the newest flyer for each store
                if target not in selected:
                    selected[target] = flyer
                else:
                    if valid_from > selected[target].get('valid_from', ''):
                        selected[target] = flyer
                break

    return selected


# =============================================================================
# ROBUST PRICE PARSING (v3.0 - now returns price_basis)
# =============================================================================

def extract_price_data(item_dict):
    """
    Robust price extraction checking multiple keys (price, sale_price, current_price).
    Returns: (price_value, price_text, price_basis)
    price_basis: 'per_lb', 'per_kg', 'per_100g', 'multi_buy', or 'each'
    """
    # 1. Find the raw price string from ANY possible key
    keys = ['price', 'current_price', 'price_text', 'sale_price', 'original_price']
    raw_price = next((item_dict[k] for k in keys if item_dict.get(k)), None)

    if not raw_price:
        return None, None, None

    text = str(raw_price).strip().lower()

    try:
        # 2. Parse the number and determine basis

        # Handle per-weight: "$3.99/lb"
        per_lb_match = re.search(r'\$?(\d+\.?\d*)\s*/\s*lb', text)
        if per_lb_match:
            return float(per_lb_match.group(1)), str(raw_price), 'per_lb'

        # Handle per-kg: "$8.80/kg"
        per_kg_match = re.search(r'\$?(\d+\.?\d*)\s*/\s*kg', text)
        if per_kg_match:
            return float(per_kg_match.group(1)), str(raw_price), 'per_kg'

        # Handle per-100g: "$1.50/100g"
        per_100g_match = re.search(r'\$?(\d+\.?\d*)\s*/\s*100\s*g', text)
        if per_100g_match:
            return float(per_100g_match.group(1)), str(raw_price), 'per_100g'

        # Handle multi-buy: "2 for $5"
        multi_match = re.search(r'(\d+)\s*(?:for|/)\s*\$?(\d+\.?\d*)', text)
        if multi_match:
            qty = float(multi_match.group(1))
            total = float(multi_match.group(2))
            if qty > 0:
                return round(total / qty, 2), str(raw_price), 'multi_buy'

        # Handle standard: "$5.99"
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", text)
        if matches:
            val = float(matches[0])
            return val, str(raw_price), 'each'

    except Exception:
        pass

    return None, str(raw_price), None


# =============================================================================
# UNIT PRICE EXTRACTION (v3.0 - uses price_text and price_basis)
# =============================================================================

def extract_unit_price(item_name, price, price_text=None, price_basis=None):
    """
    Extract unit price from item name, price text, and price basis.
    Returns: (unit_price, unit_type, grams_equivalent)

    v3.0: Now uses price_basis from extract_price_data() for much better
    coverage on proteins (which are usually priced per-lb but don't have
    weight in the item name).
    """
    if price is None or price <= 0:
        return None, None, None

    # --- Priority 1: Use price_basis from the price parser ---
    if price_basis == 'per_lb':
        kg_price = price / 0.453592  # Convert $/lb to $/kg
        return round(kg_price, 2), '$/kg', None

    if price_basis == 'per_kg':
        return round(price, 2), '$/kg', None

    if price_basis == 'per_100g':
        return round(price * 10, 2), '$/kg', None  # $/100g * 10 = $/kg

    # --- Priority 2: Check price_text for /lb or /kg patterns ---
    if price_text:
        pt_lower = str(price_text).strip().lower()
        if '/lb' in pt_lower or 'per lb' in pt_lower:
            kg_price = price / 0.453592
            return round(kg_price, 2), '$/kg', None
        if '/kg' in pt_lower or 'per kg' in pt_lower:
            return round(price, 2), '$/kg', None
        if '/100' in pt_lower and 'g' in pt_lower:
            return round(price * 10, 2), '$/kg', None

    # --- Priority 3: Parse weight/volume from item name (original logic) ---
    item_lower = item_name.lower()

    # Multi-pack: 12x100g, 6x650ml
    multi_match = re.search(r'(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(g|ml|l|oz)\b', item_lower)
    if multi_match:
        count = int(multi_match.group(1))
        unit_size = float(multi_match.group(2))
        unit = multi_match.group(3)

        # Prevent division by zero
        if count > 0 and unit_size > 0:
            if unit == 'g':
                total_g = count * unit_size
                return round(price / (total_g / 1000), 2), '$/kg', total_g
            elif unit == 'ml':
                total_ml = count * unit_size
                return round(price / (total_ml / 1000), 2), '$/L', total_ml
            elif unit == 'l':
                total_l = count * unit_size
                return round(price / total_l, 2), '$/L', total_l * 1000
            elif unit == 'oz':
                total_oz = count * unit_size
                total_g = total_oz * 28.3495
                return round(price / (total_g / 1000), 2), '$/kg', total_g

    # Weight in kg
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', item_lower)
    if kg_match:
        kg = float(kg_match.group(1))
        if kg > 0:  # Prevent division by zero
            return round(price / kg, 2), '$/kg', kg * 1000

    # Weight in grams
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*g\b', item_lower)
    if g_match:
        grams = float(g_match.group(1))
        if grams > 0:  # Prevent division by zero
            return round(price / (grams / 1000), 2), '$/kg', grams

    # Weight in lbs
    lb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lb|lbs)\b', item_lower)
    if lb_match:
        lbs = float(lb_match.group(1))
        if lbs > 0:  # Prevent division by zero
            kg = lbs * 0.453592
            return round(price / kg, 2), '$/kg', kg * 1000

    # Weight in oz
    oz_match = re.search(r'(\d+(?:\.\d+)?)\s*oz\b', item_lower)
    if oz_match:
        oz_val = float(oz_match.group(1))
        if oz_val > 0:  # Prevent division by zero
            grams = oz_val * 28.3495
            return round(price / (grams / 1000), 2), '$/kg', grams

    # Volume in liters - negative lookahead to avoid matching 'lb'
    l_match = re.search(r'(\d+(?:\.\d+)?)\s*l(?!b)\b', item_lower)
    if l_match:
        liters = float(l_match.group(1))
        if liters > 0:  # Prevent division by zero
            return round(price / liters, 2), '$/L', liters * 1000

    # Volume in ml
    ml_match = re.search(r'(\d+(?:\.\d+)?)\s*ml\b', item_lower)
    if ml_match:
        ml = float(ml_match.group(1))
        if ml > 0:  # Prevent division by zero
            return round(price / (ml / 1000), 2), '$/L', ml

    # Count: 12's, 24 pack, 6 count.
    # v3.2: require count >= 2 (a "1 pack" division is a no-op, and this
    # guards against e.g. "1L pk" if any future change reorders the unit
    # checks — currently L/ml are matched above, but the dependency was
    # implicit). Also tightened delimiters so '12pk', '12 pk' both match.
    count_match = re.search(r"(\d+)\s*(?:'s|-pack|pack|count|ct|pk)\b", item_lower)
    if count_match:
        count = int(count_match.group(1))
        if count >= 2:
            return round(price / count, 2), '$/each', count

    return None, None, None


# =============================================================================
# ITEM MATCHING HELPERS (v3.0 - improved matching logic)
# =============================================================================

def _find_historical_matches(item_row, df_history, has_norm_col=False):
    """
    Find matching items in historical data using best available key.
    Uses a three-tier approach:
      1. Exact ai_normalized_name match
      2. Keyword-overlap fuzzy match on item + normalized names
      3. Substring fallback on Item name
    Returns matching rows from history.
    """
    if df_history is None or len(df_history) == 0:
        return pd.DataFrame()

    # --- Tier 1: Exact ai_normalized_name match ---
    hist_has_norm = 'ai_normalized_name' in df_history.columns
    if has_norm_col and hist_has_norm:
        norm_name = item_row.get('ai_normalized_name', '')
        if pd.notna(norm_name) and str(norm_name).strip():
            matches = df_history[
                df_history['ai_normalized_name'] == norm_name
            ]
            if len(matches) >= 3:
                return matches

    # --- Tier 2: Keyword-overlap fuzzy match ---
    item_name = item_row['Item'] if isinstance(item_row, pd.Series) else str(item_row)
    item_str = str(item_name).lower()
    norm_str = str(norm_name).lower() if (has_norm_col and pd.notna(item_row.get('ai_normalized_name'))) else ""
    combined = f"{item_str} {norm_str}"

    skip_words = {"fresh", "the", "and", "for", "with", "size", "family", "premium",
                  "great", "value", "brand", "name", "new", "original"}
    keywords = {w for w in combined.split() if len(w) >= 3 and w not in skip_words}

    if keywords and hist_has_norm:
        hist_items = df_history['Item'].str.lower().fillna('')
        hist_norms = df_history['ai_normalized_name'].str.lower().fillna('')
        hist_combined = hist_items + " " + hist_norms

        def keyword_score(text):
            return sum(1 for kw in keywords if kw in text)

        scores = hist_combined.apply(keyword_score)
        threshold = max(2, int(len(keywords) * 0.6))
        fuzzy_matches = df_history[scores >= threshold]
        if len(fuzzy_matches) >= 2:
            return fuzzy_matches

    # --- Tier 3: Substring fallback on Item name ---
    search_term = str(item_name)[:30].lower()
    matches = df_history[
        df_history['Item'].str.lower().str.contains(search_term, na=False, regex=False)
    ]
    return matches


# =============================================================================
# HISTORICAL ANALYSIS (v3.0 - uses unit_price, improved matching)
# =============================================================================

def load_historical_data():
    """Load historical price archive."""
    if os.path.exists(HISTORICAL_ARCHIVE):
        df = pd.read_csv(HISTORICAL_ARCHIVE, low_memory=False)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        return df
    return pd.DataFrame()


def compute_historical_stats(df, df_history, lookback_days=180):
    """
    Add historical statistics to dataframe.
    v3.0: Uses ai_normalized_name for matching when available.
          Uses unit_price for comparisons when both sides have it.
    """
    if df_history is None or len(df_history) == 0:
        df['historical_min'] = None
        df['historical_max'] = None
        df['historical_avg'] = None
        df['historical_count'] = 0
        df['price_percentile'] = None
        df['is_lowest_historical'] = False
        df['pct_below_avg'] = None
        return df

    cutoff = pd.Timestamp.now() - timedelta(days=lookback_days)
    recent_history = df_history[df_history['Date'] >= cutoff].copy()

    has_norm_col = 'ai_normalized_name' in df.columns
    hist_has_unit_price = 'unit_price' in recent_history.columns

    stats = []
    for idx, row in df.iterrows():
        matches = _find_historical_matches(row, recent_history, has_norm_col=has_norm_col)

        # Determine which price column to compare
        current_unit_price = row.get('unit_price')
        current_unit_type = row.get('unit_type')
        use_unit_price = False

        if (pd.notna(current_unit_price) and current_unit_type and
                hist_has_unit_price and len(matches) > 0):
            hist_unit_matches = matches[
                (matches['unit_price'].notna()) &
                (matches['unit_type'] == current_unit_type)
            ]
            if len(hist_unit_matches) >= 2:
                matches = hist_unit_matches
                use_unit_price = True

        if use_unit_price:
            prices = matches['unit_price'].dropna()
            current_price = current_unit_price
        else:
            prices = matches['Price_Value'].dropna()
            current_price = row['Price_Value']

        prices = prices[prices > 0]

        if len(prices) >= 2:
            min_p = prices.min()
            max_p = prices.max()
            avg_p = prices.mean()

            if SCIPY_AVAILABLE:
                percentile = 100 - percentileofscore(prices, current_price)
            else:
                percentile = ((prices < current_price).sum() / len(prices)) * 100

            pct_below = ((avg_p - current_price) / avg_p) * 100 if avg_p > 0 else 0

            stats.append({
                'historical_min': round(min_p, 2),
                'historical_max': round(max_p, 2),
                'historical_avg': round(avg_p, 2),
                'historical_count': len(prices),
                'price_percentile': round(percentile, 1),
                'is_lowest_historical': current_price <= min_p,
                'pct_below_avg': round(pct_below, 1)
            })
        else:
            stats.append({
                'historical_min': None,
                'historical_max': None,
                'historical_avg': None,
                'historical_count': 0,
                'price_percentile': None,
                'is_lowest_historical': False,
                'pct_below_avg': None
            })

    stats_df = pd.DataFrame(stats)
    for col in stats_df.columns:
        df[col] = stats_df[col].values

    return df


def compute_cross_store_stats(df):
    """
    Add cross-store comparison data.
    v3.0: Uses ai_normalized_name for grouping when available.
          Uses unit_price for comparison when items share the same unit_type.
    """
    df['cross_store_rank'] = None
    df['cross_store_count'] = 1
    df['cross_store_best_price'] = None
    df['cross_store_best_store'] = None

    # Use ai_normalized_name for grouping if available
    name_col = 'ai_normalized_name' if 'ai_normalized_name' in df.columns else 'Item'

    for name in df[name_col].unique():
        if pd.isna(name) or str(name).strip() == '':
            continue

        mask = df[name_col] == name
        group = df[mask]

        if len(group['Store'].unique()) <= 1:
            continue

        # Check if we can compare via unit_price
        group_has_unit = group['unit_price'].notna() & group['unit_type'].notna()
        unit_types = group.loc[group_has_unit, 'unit_type'].unique()

        # Use unit_price if most items share the same unit_type
        if len(unit_types) == 1 and group_has_unit.sum() >= 2:
            price_col = 'unit_price'
            compare_group = group[group_has_unit]
        else:
            price_col = 'Price_Value'
            compare_group = group

        prices = compare_group.set_index(compare_group.index)[price_col].sort_values()
        best_idx = prices.idxmin()
        best_price = prices.min()
        best_store = df.loc[best_idx, 'Store']

        for rank, idx in enumerate(prices.index, 1):
            df.at[idx, 'cross_store_rank'] = rank
            df.at[idx, 'cross_store_count'] = len(prices)
            df.at[idx, 'cross_store_best_price'] = best_price
            df.at[idx, 'cross_store_best_store'] = best_store

    return df


def flag_key_value_items(df):
    """Flag key value items that shoppers track."""
    df['is_kvi'] = False

    for kvi in KEY_VALUE_ITEMS:
        mask = df['Item'].str.lower().str.contains(kvi, na=False, regex=False)
        df.loc[mask, 'is_kvi'] = True

    return df


def compute_statistical_score(df):
    """
    Compute a unified deal score based on historical, cross-store, and unit data.

    v3.0 REWRITE:
    - Base score: 40 (neutral). Range: 0-100.
    - Allows scores BELOW 50 for bad deals (above-average prices, worst cross-store).
    - No double-counting: uses pct_below_avg directly (not percentile + pct_below).
    - Bonus for unit_price availability (verified apples-to-apples comparison).
    - KVI bonus for tracked staple items.
    """
    df['deal_score'] = 40.0  # Neutral starting point

    for idx, row in df.iterrows():
        score = 40.0

        # === Component 1: Historical price position (-25 to +35) ===
        pct_below = row.get('pct_below_avg')
        if pd.notna(pct_below):
            if pct_below > 0:
                # Below average (good): up to +35 points
                score += min(35, pct_below * 0.7)
            else:
                # Above average (bad): down to -25 points
                score += max(-25, pct_below * 0.5)

        # === Component 2: Lowest-ever bonus (+10) ===
        if row.get('is_lowest_historical', False):
            score += 10

        # === Component 3: Cross-store position (-10 to +20) ===
        cross_rank = row.get('cross_store_rank')
        cross_count = row.get('cross_store_count', 1)
        if pd.notna(cross_rank) and cross_count > 1:
            rank = int(cross_rank)
            if rank == 1:
                score += 20
            elif rank == 2:
                score += 10
            elif rank == 3:
                score += 5
            else:
                score -= 10

        # === Component 4: Unit price confidence bonus (+5) ===
        if pd.notna(row.get('unit_price')):
            score += 5

        # === Component 5: Key value item bonus (+5) ===
        if row.get('is_kvi', False):
            score += 5

        df.at[idx, 'deal_score'] = round(min(100, max(0, score)), 1)

    return df


# =============================================================================
# ARCHIVE MANAGEMENT (v3.0 - saves price_basis, unit_price, unit_type)
# =============================================================================

def save_to_archive(df_current, df_archive):
    """Save current deals to historical archive."""
    if df_current.empty:
        return df_archive

    # Add date column
    df_new = df_current.copy()
    df_new['Date'] = pd.Timestamp.now().strftime('%Y-%m-%d')

    # v3.2: Fallback for missing Valid_From / Valid_Until on the flyer payload.
    # Without this, rows scrape with empty strings that become NaN and break
    # "expiring soon" sorting + history lookups.
    if 'Valid_From' in df_new.columns:
        df_new['Valid_From'] = df_new['Valid_From'].replace('', pd.NA)
        df_new['Valid_From'] = df_new['Valid_From'].fillna(df_new['Date'])
    if 'Valid_Until' in df_new.columns:
        df_new['Valid_Until'] = df_new['Valid_Until'].replace('', pd.NA)
        # If Valid_Until missing, default to Valid_From + 7 days (typical flyer window)
        vf = pd.to_datetime(df_new['Valid_From'], errors='coerce')
        fallback_vu = (vf + pd.Timedelta(days=7)).dt.strftime('%Y-%m-%d')
        df_new['Valid_Until'] = df_new['Valid_Until'].fillna(fallback_vu)

    # Select columns for archive (v3.2: also preserve Price_Text, ai_sub_category)
    archive_cols = [
        'Date', 'Store', 'Item', 'Price_Value', 'Price_Text',
        'Valid_From', 'Valid_Until',
        'price_basis', 'unit_price', 'unit_type'
    ]
    if 'ai_category' in df_new.columns:
        archive_cols.append('ai_category')
    if 'ai_normalized_name' in df_new.columns:
        archive_cols.append('ai_normalized_name')
    if 'ai_sub_category' in df_new.columns:
        archive_cols.append('ai_sub_category')

    available_cols = [c for c in archive_cols if c in df_new.columns]
    df_new = df_new[available_cols]

    # Concatenate with existing archive
    if df_archive is not None and len(df_archive) > 0:
        for col in available_cols:
            if col not in df_archive.columns:
                df_archive[col] = None

        df_archive = pd.concat([df_archive, df_new], ignore_index=True)
    else:
        df_archive = df_new

    # Remove duplicates (same store, item, price, date).
    # v3.2: dedup on a case+whitespace-normalized Item key so "Bananas" and
    # "BANANAS  " collapse to one row (without storing the lowercase form).
    before_dedup = len(df_archive)
    _item_key = df_archive['Item'].astype(str).str.strip().str.lower()
    df_archive = df_archive.assign(_dedup_item=_item_key) \
                           .drop_duplicates(subset=['Date', 'Store', '_dedup_item', 'Price_Value'], keep='last') \
                           .drop(columns=['_dedup_item'])
    removed = before_dedup - len(df_archive)

    if removed > 0:
        print(f"   Removed {removed:,} duplicate records")

    # v3.2: atomic write to avoid corrupting the only data source on crash
    _atomic_write_csv(df_archive, HISTORICAL_ARCHIVE)

    return df_archive


# =============================================================================
# MAIN SCRAPER (v3.0 - added dedup step, unified scoring)
# =============================================================================

def scrape_deals():
    """Main function to scrape and analyze grocery deals."""

    print()
    print("=" * 80)
    print("🛒 CALGARY GROCERY HUB - DEAL SCRAPER v3.1")
    print("=" * 80)
    print()

    # --- Step 1: Fetch Flyers ---
    print(f">> Scanning flyers for {POSTAL_CODE}...")
    flyers = get_flipp_flyers(POSTAL_CODE)

    if not flyers:
        print("   ⚠️ No flyers found!")
        return None

    # --- Step 2: Select Best Flyers ---
    print()
    print(">> Selecting flyers (newest GROCERY flyers)...")
    selected = select_best_flyers(flyers, TARGET_STORES)

    for store, flyer in selected.items():
        valid_from = flyer.get('valid_from', 'Unknown')[:10]
        print(f"   + {store} (Starts: {valid_from})")

    # --- Step 3: Extract Items ---
    print()
    print(">> Extracting items...")

    all_items = []

    for store, flyer in selected.items():
        flyer_id = flyer.get('id')
        items = get_flyer_items(flyer_id, store)

        for item in items:
            name = item.get('name', '').strip()
            if not name:
                continue

            # v3.0: Robust price parsing with price_basis
            price_val, price_txt, price_basis = extract_price_data(item)

            if price_val is None or price_val <= 0:
                continue

            # v3.0: Extract unit price using price_text and price_basis
            unit_price, unit_type, grams_equiv = extract_unit_price(
                name, price_val, price_text=price_txt, price_basis=price_basis
            )

            all_items.append({
                'Store': store,
                'Item': name,
                'Price_Value': price_val,
                'Price_Text': price_txt,
                'price_basis': price_basis,
                'Valid_From': flyer.get('valid_from', ''),
                'Valid_Until': flyer.get('valid_to', ''),
                'Flyer_ID': flyer_id,
                'unit_price': unit_price,
                'unit_type': unit_type,
                'grams_equivalent': grams_equiv,
            })

        print(f"   [{store}] Found {len([i for i in all_items if i['Store'] == store])} items")

    if not all_items:
        print("   ⚠️ No items extracted! (Check logic)")
        return None

    df = pd.DataFrame(all_items)
    print()
    print(f">> Extracted {len(df):,} items total")

    # --- Step 3.5: DEDUP (v3.0 - removes duplicate flyer entries) ---
    before_dedup = len(df)
    df = df.drop_duplicates(subset=['Store', 'Item', 'Price_Value'], keep='first')
    df = df.reset_index(drop=True)
    dedup_removed = before_dedup - len(df)
    if dedup_removed > 0:
        print(f"   🔄 Removed {dedup_removed} duplicate items (same store/item/price)")

    # --- Step 3.6: ITEM-LEVEL EXCLUSION (v3.0 - filter out alcohol etc.) ---
    before_filter = len(df)
    alcohol_mask = df['Item'].apply(is_alcohol_item)
    if alcohol_mask.any():
        excluded_items = df[alcohol_mask]['Item'].tolist()
        df = df[~alcohol_mask].reset_index(drop=True)
        print(f"   🚫 Filtered {len(excluded_items)} alcohol items")

    # --- Step 3.7: PER-100G CORRECTION (v3.1) ---
    df = apply_per_100g_corrections(df)

    print(f"   📊 Unique items: {len(df):,}")

    # Unit price stats
    unit_price_count = df['unit_price'].notna().sum()
    print(f"   📊 Unit prices extracted: {unit_price_count} ({unit_price_count/len(df)*100:.1f}%)")

    # Price basis stats
    if 'price_basis' in df.columns:
        basis_counts = df['price_basis'].value_counts()
        per_weight = basis_counts.get('per_lb', 0) + basis_counts.get('per_kg', 0) + basis_counts.get('per_100g', 0)
        print(f"   📊 Per-weight prices: {per_weight} | Multi-buy: {basis_counts.get('multi_buy', 0)} | Each: {basis_counts.get('each', 0)}")

    # --- Step 4: Load Historical Data ---
    print()
    print(">> Loading historical data...")
    df_history = load_historical_data()

    if len(df_history) > 0:
        print(f"   📚 Loaded {len(df_history):,} historical records")
        # v3.1: Clean per-100g entries in archive
        df_history = clean_archive_per_100g(df_history)
    else:
        print("   📚 No historical data yet (first run)")

    # --- Step 5: AI Analysis (categorization + normalization) ---
    print()
    print(">> Running AI quality analysis...")

    if AI_ANALYZER_AVAILABLE and add_ai_analysis_to_dataframe:
        try:
            df = add_ai_analysis_to_dataframe(df, df_history, batch_size=25)
        except Exception as e:
            print(f"   ⚠️ AI analysis failed: {e}")
    else:
        print("   ⚠️ AI analyzer not available - using statistical scoring only")

    # --- Step 6: Statistical Context ---
    print()
    print(">> Computing statistical context...")

    if len(df_history) > 0:
        df = compute_historical_stats(df, df_history)
        hist_count = (df['historical_count'] > 0).sum()
        print(f"   📈 Items with historical data: {hist_count} ({hist_count/len(df)*100:.1f}%)")

    df = compute_cross_store_stats(df)
    cross_count = (df['cross_store_count'] > 1).sum()
    print(f"   🏪 Items at multiple stores: {cross_count}")

    df = flag_key_value_items(df)
    kvi_count = df['is_kvi'].sum()
    print(f"   ⭐ Key Value Items flagged: {kvi_count}")

    # --- Step 6.5: Unified Scoring (v3.0) ---
    df = compute_statistical_score(df)

    score_col = 'deal_score'
    hot = (df[score_col] >= 85).sum()
    good = ((df[score_col] >= 70) & (df[score_col] < 85)).sum()
    fair = ((df[score_col] >= 50) & (df[score_col] < 70)).sum()
    below = ((df[score_col] >= 30) & (df[score_col] < 50)).sum()
    poor = (df[score_col] < 30).sum()
    print(f"   📊 Score distribution: 🔥Hot={hot} | ✅Good={good} | 😐Fair={fair} | ⚠️Below={below} | ❌Poor={poor}")

    # --- Step 7: Show Top Deals ---
    print()
    print(">> Top Deals (by deal_score):")

    top_deals = df.nlargest(10, 'deal_score')
    for _, row in top_deals.iterrows():
        lowest = "🎯 LOWEST" if row.get('is_lowest_historical', False) else ""
        unit_info = f" ({row['unit_type']})" if pd.notna(row.get('unit_type')) else ""
        print(f"   {row['Item'][:45]:45} ${row['Price_Value']:6.2f}{unit_info:8} @ {row['Store'][:18]:18} Score: {row['deal_score']:.0f} {lowest}")

    # --- Step 8: Save Data ---
    print()
    print(">> Saving data...")

    # Save to archive
    df_archive = save_to_archive(df, df_history)
    print(f"   📚 Historical archive: {len(df_archive):,} total records")

    # Save current flyers (atomic: tempfile + os.replace)
    _atomic_write_csv(df, CURRENT_FLYERS)
    print(f"   📋 Current flyers: {len(df):,} active deals")

    return df


if __name__ == "__main__":
    df = scrape_deals()