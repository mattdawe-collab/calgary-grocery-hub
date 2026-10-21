"""
Calgary Grocery Hub - AI Quality Analyzer v5.0
Categorization + normalization via the local Claude Code CLI (subscription).

Updates:
- v5.0: Backend moved to Claude Code CLI (`claude -p`), see ai_backends.py
    * Gemini 2.5 thinking tokens truncated every batch Jun-Sep 2026; fixed
      config kept as an opt-in paid fallback
    * Name-keyed cache reuses earlier classifications (no LLM call)
    * Results matched by item name; parallel batches (AI_WORKERS)
- v4.0: Migrated from Gemini to Claude (Anthropic) API
    * Uses anthropic SDK with claude-haiku-4-5-20251001
    * Structured JSON output via system prompt
    * Rate limit retry via anthropic.RateLimitError
- v3.0: Major overhaul:
    * Prompt provides explicit normalization examples (strip brands, standardize cuts)
    * Scoring constrained by statistical rubric (must follow data-driven thresholds)
    * Includes price_basis and unit_price in context sent to AI
    * Dedup-aware: skips already-scored items more reliably
    * Statistical fallback scoring aligned with get_deals.py formula (base 40, allows sub-50)
"""

import pandas as pd
import numpy as np
import os
import sys
import json
import re
import time
import random
from dotenv import load_dotenv
from datetime import datetime, timedelta
from data_quality import parse_dates, repair_category
from ai_backends import (
    ClaudeCLIError,
    anthropic_model,
    anthropic_request_kwargs,
    response_text,
    is_backend_unusable,
    claude_cli_model,
    extract_json_array,
    run_claude_cli,
    select_backend,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path, override=True)

# Optional progress bar
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    class tqdm:
        def __init__(self, *args, **kwargs):
            self.total = kwargs.get('total', 0)
            self.n = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def update(self, n=1): self.n += n

# Gemini SDK (default)
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Claude SDK (fallback)
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

if not GEMINI_AVAILABLE and not CLAUDE_AVAILABLE:
    print("   ⚠️ No AI SDK installed - will use statistical scoring only")

# --- CONFIGURATION ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Taxonomy matching dashboard.py
TAXONOMY = {
    "Produce": ["Fruit", "Vegetables", "Herbs", "Pre-cut Fruit/Veg", "Salad Kits"],
    "Beef": ["Steak", "Ground Beef", "Roast", "Ribs", "Burgers", "Other Beef"],
    "Pork": ["Chops", "Roast", "Ribs", "Bacon", "Ham", "Ground Pork", "Sausage (Fresh)", "Other Pork"],
    "Poultry": ["Chicken Breast", "Chicken Thighs/Legs", "Whole Chicken", "Wings", "Turkey", "Ground Poultry", "Sausage (Poultry)"],
    "Lamb": ["Chops", "Leg", "Ground", "Other Lamb"],
    "Seafood": ["Fish Fillets", "Whole Fish", "Shrimp/Prawns", "Shellfish", "Smoked/Cured", "Prepared Seafood"],
    "Dairy & Eggs": ["Milk", "Cheese (Block)", "Cheese (Shredded/Sliced)", "Yogurt", "Butter/Margarine", "Eggs", "Cream", "Sour Cream"],
    "Bakery": ["Bread", "Buns/Rolls", "Tortillas/Wraps", "Desserts/Cakes", "Pastries/Donuts", "Bagels/Muffins"],
    "Pantry": ["Canned Goods", "Pasta/Grains", "Rice", "Sauces/Condiments", "Spices/Oils", "Baking Supplies", "Breakfast/Cereal", "Soups"],
    "Frozen": ["Pizza", "Fruit/Vegetables", "Meals/Entrees", "Ice Cream/Dessert", "Meat/Seafood (Frozen)", "Breakfast (Frozen)"],
    "Beverages": ["Water", "Soda/Pop", "Juice", "Coffee", "Tea", "Energy/Sports Drinks", "Plant-Based Milk"],
    "Household & Personal": ["Cleaning Supplies", "Paper Products", "Laundry", "Personal Care", "Health/Pharmacy", "Pet Food/Supplies", "Baby"],
    "Snacks": ["Chips/Pretzels", "Crackers", "Candy/Chocolate", "Nuts/Seeds", "Cookies", "Bars/Granola"],
    "Other": ["General", "Floral", "Automotive", "Seasonal", "Deli (Prepared)"]
}

# Rating thresholds
RATING_THRESHOLDS = {
    'hot_deal': 85,
    'good_buy': 70,
    'fair': 50,
    'below_average': 30,
    'poor': 0
}

# Category keywords for fallback classification
CATEGORY_KEYWORDS = {
    'Produce': ['apple', 'banana', 'orange', 'grape', 'berry', 'strawberry', 'blueberry',
                'lettuce', 'spinach', 'kale', 'broccoli', 'carrot', 'potato', 'tomato',
                'onion', 'pepper', 'cucumber', 'celery', 'mushroom', 'avocado', 'mango',
                'lemon', 'lime', 'peach', 'pear', 'plum', 'melon', 'watermelon',
                'zucchini', 'squash', 'asparagus', 'corn', 'peas', 'beans', 'cabbage'],
    'Beef': ['beef', 'steak', 'ground beef', 'sirloin', 'ribeye', 'tenderloin', 'brisket',
             'eye of round', 'chuck', 'flank', 'prime rib', 'strip loin', 't-bone'],
    'Pork': ['pork', 'bacon', 'ham', 'pork chop', 'pork loin', 'pork tenderloin',
             'pork belly', 'back ribs', 'side ribs', 'pork shoulder'],
    'Poultry': ['chicken', 'turkey', 'duck', 'chicken breast', 'chicken thigh',
                'chicken wing', 'drumstick', 'whole chicken', 'cornish hen'],
    'Lamb': ['lamb', 'lamb chop', 'lamb leg', 'lamb shoulder', 'rack of lamb'],
    'Seafood': ['salmon', 'shrimp', 'fish', 'tuna', 'cod', 'tilapia', 'halibut',
                'prawn', 'crab', 'lobster', 'haddock', 'sole', 'trout', 'scallop',
                'mussel', 'clam', 'pollock', 'basa', 'snapper'],
    'Dairy & Eggs': ['milk', 'cheese', 'yogurt', 'butter', 'egg', 'cream', 'sour cream',
                     'margarine', 'whipping cream', 'cottage cheese'],
    'Bakery': ['bread', 'bagel', 'muffin', 'croissant', 'bun', 'roll', 'tortilla', 'pita',
               'naan', 'wrap', 'english muffin', 'ciabatta'],
    'Pantry': ['pasta', 'rice', 'cereal', 'soup', 'sauce', 'oil', 'flour', 'sugar',
               'canned', 'peanut butter', 'jam', 'honey', 'vinegar', 'broth'],
    'Frozen': ['frozen', 'ice cream', 'pizza', 'frozen dinner', 'popsicle', 'gelato'],
    'Beverages': ['juice', 'soda', 'pop', 'water', 'coffee', 'tea', 'energy drink',
                  'protein shake', 'kombucha', 'sparkling'],
    'Snacks': ['chip', 'chips', 'cracker', 'cookie', 'candy', 'chocolate', 'pretzel',
               'popcorn', 'nuts', 'granola bar', 'trail mix', 'rice cake'],
    'Household & Personal': ['soap', 'shampoo', 'detergent', 'paper towel', 'toilet paper',
                              'toothpaste', 'diaper', 'cleaning', 'laundry', 'deodorant',
                              'garbage bag', 'dish soap', 'fabric softener']
}

# Sausage requires special handling (could be pork or poultry)
SAUSAGE_KEYWORDS_PORK = ['pork sausage', 'bratwurst', 'italian sausage', 'kolbassa',
                          'kielbasa', 'chorizo', 'johnsonville']
SAUSAGE_KEYWORDS_POULTRY = ['chicken sausage', 'turkey sausage']


def get_historical_context(item_name, df_history, lookback_days=180):
    """
    Get historical price statistics for an item.
    v3.0: Uses ai_normalized_name when available in history.
    """
    if df_history is None or len(df_history) == 0:
        return None

    # Ensure Date column is datetime
    if 'Date' in df_history.columns and not pd.api.types.is_datetime64_any_dtype(df_history['Date']):
        df_history = df_history.copy()
        df_history['Date'] = parse_dates(df_history['Date'])

    cutoff = pd.Timestamp.now() - timedelta(days=lookback_days)

    if 'Date' in df_history.columns:
        recent = df_history[df_history['Date'] >= cutoff]
    else:
        recent = df_history

    # Find matching items (use first 30 chars for broader matching)
    search_term = item_name[:30].lower()
    matches = recent[recent['Item'].str.lower().str.contains(search_term, na=False, regex=False)]

    if len(matches) < 2:
        return None

    prices = matches['Price_Value'].dropna()
    prices = prices[prices > 0]

    if len(prices) < 2:
        return None

    return {
        'avg': round(prices.mean(), 2),
        'min': round(prices.min(), 2),
        'max': round(prices.max(), 2),
        'count': len(prices)
    }


def get_cross_store_context(item_name, df_current):
    """
    Find the same item at other stores.
    v3.0: Uses ai_normalized_name for matching when available.
    """
    if df_current is None or len(df_current) == 0:
        return None

    # Try normalized name first
    if 'ai_normalized_name' in df_current.columns:
        # Find this item's normalized name
        item_mask = df_current['Item'] == item_name
        if item_mask.any():
            norm_name = df_current.loc[item_mask, 'ai_normalized_name'].iloc[0]
            if pd.notna(norm_name) and str(norm_name).strip():
                norm_matches = df_current[df_current['ai_normalized_name'] == norm_name]
                if len(norm_matches) >= 2:
                    stores = norm_matches.groupby('Store')['Price_Value'].min().to_dict()
                    if len(stores) >= 2:
                        return {
                            'stores': stores,
                            'best_price': min(stores.values()),
                            'best_store': min(stores, key=stores.get)
                        }

    # Fallback: substring match on first 30 chars
    search_term = item_name[:30].lower()
    matches = df_current[df_current['Item'].str.lower().str.contains(search_term, na=False, regex=False)]

    if len(matches) < 2:
        return None

    stores = matches.groupby('Store')['Price_Value'].min().to_dict()
    if len(stores) < 2:
        return None

    return {
        'stores': stores,
        'best_price': min(stores.values()),
        'best_store': min(stores, key=stores.get)
    }


def categorize_by_keywords(item_name):
    """Fallback categorization using keywords."""
    repaired_category, _ = repair_category(item_name, None)
    if repaired_category != "Other":
        return repaired_category

    item_lower = item_name.lower()

    # Check sausage first (special handling)
    for keyword in SAUSAGE_KEYWORDS_POULTRY:
        if keyword in item_lower:
            return 'Poultry'
    for keyword in SAUSAGE_KEYWORDS_PORK:
        if keyword in item_lower:
            return 'Pork'
    if 'sausage' in item_lower:
        return 'Pork'  # Default sausage to pork

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, item_lower):
                return category

    return 'Other'


def compute_statistical_score(price, hist_context, cross_context):
    """
    Compute a deal score based purely on statistics.
    v3.0: Aligned with get_deals.py formula. Base 40, allows sub-50.
    """
    score = 40  # Neutral starting point

    if hist_context:
        avg = hist_context['avg']
        min_p = hist_context['min']

        # Historical price position (-25 to +35)
        if avg > 0:
            pct_below = ((avg - price) / avg) * 100
            if pct_below > 0:
                score += min(35, pct_below * 0.7)
            else:
                score += max(-25, pct_below * 0.5)

        # Lowest ever bonus (+10)
        if price <= min_p:
            score += 10

    if cross_context:
        best = cross_context['best_price']
        stores = cross_context['stores']

        # Cross-store position (-10 to +20)
        if price <= best:
            score += 20
        elif len(stores) > 1:
            prices_sorted = sorted(stores.values())
            if price in prices_sorted:
                rank = prices_sorted.index(price) + 1
            else:
                rank = len(prices_sorted)

            if rank == 2:
                score += 10
            elif rank == 3:
                score += 5
            else:
                score -= 10

    return max(0, min(100, int(score)))


def generate_statistical_explanation(price, hist_context, cross_context):
    """Generate explanation based on statistics."""
    parts = []

    if hist_context:
        avg = hist_context['avg']
        min_p = hist_context['min']

        if price <= min_p:
            parts.append(f"LOWEST PRICE in 6 months (usually ${avg:.2f})")
        elif avg > 0:
            pct = ((avg - price) / avg) * 100
            if pct > 15:
                parts.append(f"{pct:.0f}% below 6-month avg of ${avg:.2f}")
            elif pct > 0:
                parts.append(f"Slightly below avg (${avg:.2f})")
            elif pct > -10:
                parts.append(f"Near average (${avg:.2f})")
            else:
                parts.append(f"Above average (usually ${avg:.2f})")

    if cross_context:
        best = cross_context['best_price']
        best_store = cross_context['best_store']

        if price <= best:
            parts.append(f"Best price across {len(cross_context['stores'])} stores")
        else:
            parts.append(f"${best:.2f} at {best_store}")

    if not parts:
        return "Standard pricing (no historical data)"

    return ". ".join(parts)


def get_rating_from_score(score):
    """Convert numeric score to rating label."""
    if score >= RATING_THRESHOLDS['hot_deal']:
        return "🔥 Hot Deal"
    elif score >= RATING_THRESHOLDS['good_buy']:
        return "✅ Good Buy"
    elif score >= RATING_THRESHOLDS['fair']:
        return "😐 Fair"
    elif score >= RATING_THRESHOLDS['below_average']:
        return "⚠️ Below Average"
    else:
        return "❌ Poor Value"


def _build_analysis_prompt(batch_data, taxonomy_str):
    """Build the prompt for deal analysis."""
    return f"""Analyze these grocery items and return a JSON array.

TAXONOMY (use ONLY these categories and subcategories):
{taxonomy_str}

ITEMS TO ANALYZE:
{json.dumps(batch_data, indent=2)}

For each item, return a JSON object with these fields:

1. "item": the original item name (unchanged)

2. "category": main category from taxonomy

3. "subcategory": subcategory from taxonomy

4. "normalized_name": A GENERIC product identity with brand stripped. This is critical for cross-store matching.
   RULES:
   - REMOVE brand names (No Name, Compliments, Great Value, Maple Leaf, etc.)
   - REMOVE package sizes (500g, 908g, etc.) - we track size separately
   - KEEP the cut/type (boneless, split, lean, medium, etc.)
   - STANDARDIZE to common names
   Examples:
     "NO NAME® BACON, 500 g" → "Bacon"
     "COMPLIMENTS Fresh AIR-CHILLED Split Chicken Wings" → "Chicken Wings (Split)"
     "Your Fresh Market™ fresh medium ground beef value pack" → "Ground Beef (Medium)"
     "Fresh Atlantic Salmon Fillets" → "Salmon Fillets (Atlantic)"
     "MAPLE LEAF Natural Bacon or Ready Crisp Fully Cooked Bacon" → "Bacon (Natural)"
     "Gala Apples" → "Apples (Gala)"
     "Kraft Peanut Butter 1 kg" → "Peanut Butter"
     "Great Value sliced bacon" → "Bacon (Sliced)"
     "IQF FROZEN SPLIT CHICKEN WINGS" → "Chicken Wings (Split, Frozen)"
     "HALAL CHICKEN WINGS" → "Chicken Wings (Halal)"
   If the item lists multiple different products (e.g., "X or Y"), use only the FIRST product.

5. "score": deal score 0-100. You MUST follow this rubric based on the data provided:
   - If history.avg is provided: score = 40 + (pct_below_avg * 0.7) where pct_below_avg = (avg - price) / avg * 100
   - If price <= history.min: add +10
   - If cross_store shows this is the best price: add +20
   - If cross_store shows this is NOT the best: add +5 to +10 depending on rank
   - If no data: score should be 40-50 (neutral)
   - Scores CAN be below 50 for above-average prices

6. "rating": based on score: "🔥 Hot Deal" (85+), "✅ Good Buy" (70-84), "😐 Fair" (50-69), "⚠️ Below Average" (30-49), "❌ Poor Value" (<30)

7. "explanation": Brief explanation with SPECIFIC NUMBERS from the data (e.g., "38% below avg of $5.99, best of 3 stores")

Return ONLY a valid JSON array, no other text."""


def _parse_ai_response(text):
    """Parse a model reply into a list, tolerating fences/prose. Raises ValueError if truncated."""
    return extract_json_array(text)


def _gemini_scoring_config():
    """Gemini generation config for scoring.

    gemini-2.5-flash is a "thinking" model: its reasoning tokens are charged
    against max_output_tokens. With the old 4096 cap the JSON was cut off after
    ~450 characters on every batch (Jun-Sep 2026). Disable thinking for this
    mechanical task, force JSON output, and give it room.
    """
    return {
        "max_output_tokens": 16384,
        "temperature": 0.15,
        "response_mime_type": "application/json",
        "thinking_config": {"thinking_budget": 0},
    }


def _is_non_retryable_api_error(error):
    """Return True for permanent API failures that should not burn retries."""
    text = f"{type(error).__name__}: {error}".lower()
    permanent_markers = [
        "404",
        "not_found",
        "not found",
        "no longer available",
        "invalid_argument",
        "permission_denied",
        "spending cap",
        "spend cap",
        "model",
    ]
    transient_markers = ["429", "rate", "503", "unavailable", "timeout", "deadline"]
    if "spending cap" in text or "spend cap" in text:
        return True
    return any(m in text for m in permanent_markers) and not any(m in text for m in transient_markers)


def call_ai_api(batch_data, taxonomy_str, ai_client):
    """
    Call the configured AI backend with retry logic and return a list of
    per-item dicts, or None on failure (caller falls back to statistics).

    ai_client is a dict with 'type' ('claude_code' | 'gemini' | 'anthropic')
    and, for API backends, a 'client' object.
    """

    prompt = _build_analysis_prompt(batch_data, taxonomy_str)
    system_msg = "You are a grocery deal analyst for Calgary, Canada. Respond with ONLY a valid JSON array. No markdown fences, no explanatory text."
    backend = ai_client['type']

    max_retries = 3 if backend == 'claude_code' else 5
    base_delay = 1

    for attempt in range(max_retries):
        try:
            if backend == 'claude_code':
                text = run_claude_cli(f"{system_msg}\n\n{prompt}", model=claude_cli_model("scoring"))
                return _parse_ai_response(text)
            elif backend == 'gemini':
                response = ai_client['client'].models.generate_content(
                    model=GEMINI_MODEL,
                    contents=f"{system_msg}\n\n{prompt}",
                    config=genai.types.GenerateContentConfig(**_gemini_scoring_config()),
                )
                return _parse_ai_response(response.text)
            else:
                # No temperature: current models reject sampling parameters
                # ("`temperature` is deprecated for this model", 400).
                response = ai_client['client'].messages.create(**anthropic_request_kwargs(
                    model=anthropic_model("scoring"),
                    system=system_msg,
                    prompt=prompt,
                    max_tokens=16384,
                    effort=os.getenv("ANTHROPIC_SCORING_EFFORT", "low"),
                ))
                return _parse_ai_response(response_text(response))

        except (json.JSONDecodeError, ValueError) as e:
            # Truncated or malformed output. Retry once (models are non-deterministic),
            # then fall back so the run keeps moving.
            if attempt < 1:
                print(f"      ⚠️ AI returned invalid JSON ({e}); retrying once...")
                continue
            print(f"      ❌ AI returned invalid JSON, using statistical fallback: {e}")
            return None
        except ClaudeCLIError as e:
            msg = str(e)
            if "authenticate" in msg.lower() or "logged in" in msg.lower():
                print(f"      ❌ Claude CLI auth failure, not retrying: {msg}")
                return None
            if attempt < max_retries - 1:
                print(f"      ⚠️ Claude CLI error: {msg}. Retrying...")
                time.sleep(base_delay * (2 ** attempt))
            else:
                print(f"      ❌ Claude CLI failed after {max_retries} attempts: {msg}")
                return None
        except Exception as e:
            err_name = type(e).__name__
            if is_backend_unusable(e):
                # No credits, bad key, no permission: every retry fails the
                # same way, and 35 batches x 5 retries is a long way to learn
                # nothing. Fall back now.
                print(f"      \u274c Backend unavailable, not retrying: {e}")
                return None
            if _is_non_retryable_api_error(e):
                print(f"      ❌ API permanent error, not retrying: {e}")
                return None
            if 'RateLimit' in err_name or '429' in str(e):
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"      ⏳ Rate limit hit. Retrying in {delay:.1f}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                else:
                    print(f"      ❌ API rate limit exceeded after {max_retries} attempts")
                    return None
            elif attempt < max_retries - 1:
                print(f"      ⚠️ API Error: {e}. Retrying...")
                time.sleep(2)
            else:
                print(f"      ❌ API Failed after {max_retries} attempts: {e}")
                return None
    return None


# =============================================================================
# NAME-KEYED CATEGORIZATION CACHE
# =============================================================================

def _norm_key(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def build_name_cache(df_history):
    """
    Map normalized item name -> {category, subcategory, normalized_name} from
    archive rows that carry genuine AI output.

    Statistical-fallback rows are recognisable (normalized_name == Item and
    subcategory == 'General') and are excluded, so garbage from the
    Jun-Sep 2026 outage never gets cached. Newest row per name wins.
    """
    if df_history is None or len(df_history) == 0:
        return {}
    needed = {'Item', 'ai_normalized_name', 'ai_category', 'ai_sub_category'}
    if not needed.issubset(df_history.columns):
        return {}

    h = df_history[list(needed) + (['Date'] if 'Date' in df_history.columns else [])].copy()
    h = h.dropna(subset=['ai_normalized_name', 'ai_category'])
    item_key = h['Item'].map(_norm_key)
    norm_key = h['ai_normalized_name'].map(_norm_key)
    sub = h['ai_sub_category'].astype(str).str.strip()
    cat = h['ai_category'].astype(str).str.strip()
    trusted = (norm_key != item_key) & (norm_key != '') & (sub != '') & (sub != 'General') & (cat != '') & (cat != 'Other')
    h = h[trusted]
    if h.empty:
        return {}
    if 'Date' in h.columns:
        h = h.assign(_d=parse_dates(h['Date'])).sort_values('_d')
    cache = {}
    for _, row in h.iterrows():
        cache[_norm_key(row['Item'])] = {
            'category': str(row['ai_category']).strip(),
            'subcategory': str(row['ai_sub_category']).strip(),
            'normalized_name': str(row['ai_normalized_name']).strip(),
        }
    return cache


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def _make_ai_client(backend_type):
    """Instantiate an API client for the chosen backend; None means statistical."""
    if backend_type == 'claude_code':
        print(f"   🤖 Using Claude Code CLI: {claude_cli_model('scoring')}")
        return {'type': 'claude_code'}
    if backend_type == 'gemini' and GEMINI_AVAILABLE:
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            print(f"   🤖 Using Gemini: {GEMINI_MODEL}")
            return {'type': 'gemini', 'client': client}
        except Exception as e:
            print(f"   ⚠️ Failed to configure Gemini: {e}")
    if backend_type == 'anthropic' and CLAUDE_AVAILABLE:
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            print(f"   🤖 Using Claude API: {anthropic_model('scoring')}")
            return {'type': 'anthropic', 'client': client}
        except Exception as e:
            print(f"   ⚠️ Failed to configure Claude API: {e}")
    return None


def _apply_ai_result(df_current, idx, ai_result, source):
    df_current.at[idx, 'ai_category'] = ai_result.get('category', 'Other')
    df_current.at[idx, 'ai_sub_category'] = ai_result.get('subcategory', 'General')
    df_current.at[idx, 'ai_normalized_name'] = ai_result.get('normalized_name', '')
    df_current.at[idx, 'ai_deal_score'] = ai_result.get('score', 50)
    df_current.at[idx, 'ai_deal_rating'] = ai_result.get('rating', '😐 Fair')
    df_current.at[idx, 'ai_explanation'] = ai_result.get('explanation', '')
    df_current.at[idx, 'ai_confidence'] = source


def _apply_statistical(df_current, idx, ctx, source='statistical', cached=None):
    row = df_current.loc[idx]
    hist = ctx.get('historical')
    cross = ctx.get('cross_store')
    score = compute_statistical_score(row['Price_Value'], hist, cross)
    df_current.at[idx, 'ai_deal_score'] = score
    df_current.at[idx, 'ai_deal_rating'] = get_rating_from_score(score)
    df_current.at[idx, 'ai_explanation'] = generate_statistical_explanation(row['Price_Value'], hist, cross)
    if cached:
        df_current.at[idx, 'ai_category'] = cached['category']
        df_current.at[idx, 'ai_sub_category'] = cached['subcategory']
        df_current.at[idx, 'ai_normalized_name'] = cached['normalized_name']
    else:
        df_current.at[idx, 'ai_category'] = categorize_by_keywords(row['Item'])
        df_current.at[idx, 'ai_sub_category'] = 'General'
        df_current.at[idx, 'ai_normalized_name'] = row['Item']
    df_current.at[idx, 'ai_confidence'] = source


def _build_batch_payload(df_current, batch_indices, context_cache):
    batch_data = []
    for idx in batch_indices:
        row = df_current.loc[idx]
        ctx = context_cache.get(idx, {})
        hist = ctx.get('historical')
        cross = ctx.get('cross_store')
        item_data = {'item': row['Item'], 'price': row['Price_Value'], 'store': row['Store']}
        if pd.notna(row.get('price_basis')):
            item_data['price_basis'] = row['price_basis']
        if pd.notna(row.get('unit_price')):
            item_data['unit_price'] = row['unit_price']
            item_data['unit_type'] = row.get('unit_type', '')
        if hist:
            item_data['history'] = hist
        if cross:
            item_data['cross_store'] = {
                'best_price': cross['best_price'],
                'best_store': cross['best_store'],
                'num_stores': len(cross['stores']),
            }
        batch_data.append(item_data)
    return batch_data


def _match_results(batch_indices, batch_data, ai_results):
    """
    Pair AI results with dataframe rows by item name (models reorder and
    occasionally drop items). Returns {idx: result}. Unmatched rows are absent.
    """
    if not ai_results:
        return {}
    by_name = {}
    for res in ai_results:
        if isinstance(res, dict):
            by_name.setdefault(_norm_key(res.get('item')), []).append(res)
    matched = {}
    for idx, data in zip(batch_indices, batch_data):
        bucket = by_name.get(_norm_key(data['item']))
        if bucket:
            matched[idx] = bucket.pop(0)
    # Positional fallback only when names failed entirely but counts line up.
    if not matched and len(ai_results) == len(batch_indices) and all(isinstance(r, dict) for r in ai_results):
        matched = dict(zip(batch_indices, ai_results))
    return matched


def add_ai_analysis_to_dataframe(df_current, df_history=None, batch_size=25):
    """
    Add AI-powered categorization/normalization to the deals dataframe.

    Backend order (see ai_backends.select_backend): Claude Code CLI (subscription)
    -> paid API only if AI_ALLOW_PAID_FALLBACK=1 -> statistical.
    Items whose exact name was classified in an earlier run reuse that
    classification without an LLM call.
    """
    load_dotenv(dotenv_path, override=True)

    ai_columns = [
        'ai_deal_score', 'ai_deal_rating', 'ai_explanation',
        'ai_normalized_name', 'ai_category', 'ai_sub_category',
        'ai_confidence'
    ]
    for col in ai_columns:
        if col not in df_current.columns:
            df_current[col] = 0.0 if col == 'ai_deal_score' else ''

    if df_current.empty:
        return df_current

    backend = select_backend(verbose=True)
    ai_client = _make_ai_client(backend['type'])
    use_ai = ai_client is not None
    if not use_ai:
        print("   📊 No usable AI backend - using statistical scoring only")

    if df_history is not None and len(df_history) > 0 and 'Date' in df_history.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_history['Date']):
            df_history = df_history.copy()
            df_history['Date'] = parse_dates(df_history['Date'])

    items_to_score = df_current[
        (df_current['ai_deal_score'].isnull()) |
        (df_current['ai_deal_score'] == 0) |
        (df_current['ai_deal_score'] == 0.0)
    ]
    if items_to_score.empty:
        print("   ✅ All items already scored")
        return df_current

    print(f"   📝 Scoring {len(items_to_score)} items...")

    context_cache = {}
    for idx, row in items_to_score.iterrows():
        hist_ctx = get_historical_context(row['Item'], df_history) if df_history is not None else None
        cross_ctx = get_cross_store_context(row['Item'], df_current)
        context_cache[idx] = {'historical': hist_ctx, 'cross_store': cross_ctx}

    # --- Cache pass: reuse prior classifications for identical item names ---
    name_cache = build_name_cache(df_history) if (use_ai and os.getenv("AI_NAME_CACHE", "1") != "0") else {}
    cached_hits = 0
    llm_indices = []
    for idx in items_to_score.index:
        cached = name_cache.get(_norm_key(df_current.at[idx, 'Item']))
        if cached:
            _apply_statistical(df_current, idx, context_cache[idx], source='cached', cached=cached)
            cached_hits += 1
        else:
            llm_indices.append(idx)
    if name_cache:
        print(f"   💾 Name cache: {cached_hits} items reused prior classification, {len(llm_indices)} need the model")

    if not use_ai:
        for idx in llm_indices:
            _apply_statistical(df_current, idx, context_cache[idx])
        llm_indices = []

    # --- Model pass ---
    batch_size = int(os.getenv("AI_BATCH_SIZE", batch_size))
    taxonomy_str = json.dumps(TAXONOMY, indent=2)
    batches = [llm_indices[i:i + batch_size] for i in range(0, len(llm_indices), batch_size)]
    total_batches = len(batches)
    workers = int(os.getenv("AI_WORKERS", "3" if backend['type'] == 'claude_code' else "1"))
    workers = max(1, min(workers, total_batches or 1))

    def run_batch(batch_num, batch_indices):
        batch_data = _build_batch_payload(df_current, batch_indices, context_cache)
        results = call_ai_api(batch_data, taxonomy_str, ai_client) if use_ai else None
        return batch_num, batch_indices, batch_data, results

    def consume(batch_num, batch_indices, batch_data, results):
        matched = _match_results(batch_indices, batch_data, results)
        for idx in batch_indices:
            if idx in matched:
                _apply_ai_result(df_current, idx, matched[idx], ai_client['type'])
            else:
                _apply_statistical(df_current, idx, context_cache[idx])
        missing = len(batch_indices) - len(matched)
        status = "✅" if not missing else ("⚠️ Using statistical fallback" if not matched else f"⚠️ {missing} item(s) missing, statistical for those")
        print(f"   📦 Batch {batch_num}/{total_batches} ({len(batch_indices)} items)... {status}")

    if workers > 1 and total_batches > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_batch, n + 1, b) for n, b in enumerate(batches)]
            for fut in as_completed(futures):
                consume(*fut.result())
    else:
        for n, b in enumerate(batches):
            consume(*run_batch(n + 1, b))

    # Surface AI vs fallback split so silent degradation is visible.
    total = len(df_current)
    conf = df_current['ai_confidence']
    fb = int((conf == 'statistical').sum())
    ai_n = int(conf.isin(['claude_code', 'gemini', 'anthropic', 'claude']).sum())
    cached_n = int((conf == 'cached').sum())
    pct = fb / total * 100 if total else 0
    print(f"   📊 Classification sources: model {ai_n:,} | cached {cached_n:,} | statistical {fb:,} ({pct:.1f}%)")
    if use_ai and pct > 10:
        print(f"   ⚠️ ALERT: high statistical-fallback rate ({pct:.1f}%) - check the AI backend / login")

    print("   ✅ Scoring complete")
    return df_current

if __name__ == "__main__":
    # Test with sample data
    print("AI Quality Analyzer v5.0 - Claude Code CLI Edition")
    print(f"Scoring model: {claude_cli_model('scoring')}  |  Gemini: {GEMINI_MODEL}  |  Claude API: {CLAUDE_MODEL}")
    print(f"Backend: {select_backend()}")
