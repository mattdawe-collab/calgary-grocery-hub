"""
Calgary Grocery Hub - AI Quality Analyzer v4.0
Uses Claude Haiku for HIGH SPEED deal analysis

Updates:
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
import json
import re
import time
import random
from dotenv import load_dotenv
from datetime import datetime, timedelta

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
GEMINI_MODEL = "gemini-2.0-flash"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

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
        df_history['Date'] = pd.to_datetime(df_history['Date'], errors='coerce')

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
    """Parse and clean AI response text into JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    return json.loads(text)


def call_ai_api(batch_data, taxonomy_str, ai_client):
    """
    Call AI API (Gemini default, Claude fallback) with retry logic.
    ai_client is a dict with 'type' and 'client' keys.
    """

    prompt = _build_analysis_prompt(batch_data, taxonomy_str)
    system_msg = "You are a grocery deal analyst for Calgary, Canada. Respond with ONLY a valid JSON array. No markdown fences, no explanatory text."

    max_retries = 5
    base_delay = 1

    for attempt in range(max_retries):
        try:
            if ai_client['type'] == 'gemini':
                response = ai_client['client'].models.generate_content(
                    model=GEMINI_MODEL,
                    contents=f"{system_msg}\n\n{prompt}",
                    config=genai.types.GenerateContentConfig(
                        max_output_tokens=4096,
                        temperature=0.15,
                    )
                )
                return _parse_ai_response(response.text)
            else:
                response = ai_client['client'].messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    temperature=0.15,
                    system=system_msg,
                    messages=[{"role": "user", "content": prompt}]
                )
                return _parse_ai_response(response.content[0].text)

        except Exception as e:
            err_name = type(e).__name__
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

        except Exception as e:
            print(f"      ❌ Unexpected error: {e}")
            return None


def add_ai_analysis_to_dataframe(df_current, df_history=None, batch_size=25):
    """
    Add AI-powered analysis to the deals dataframe using Claude.
    Falls back to statistical scoring if no API key is available.

    v4.0: Migrated from Gemini to Claude (Anthropic).
    v3.0: Includes price_basis and unit_price in context sent to AI.
          AI is now focused on categorization + normalization.
          Scoring follows a constrained rubric.
    """
    load_dotenv(override=True)

    # Initialize columns (v4.1: trimmed dead columns)
    ai_columns = [
        'ai_deal_score', 'ai_deal_rating', 'ai_explanation',
        'ai_normalized_name', 'ai_category', 'ai_sub_category',
        'ai_confidence'
    ]

    for col in ai_columns:
        if col not in df_current.columns:
            if col == 'ai_deal_score':
                df_current[col] = 0.0
            else:
                df_current[col] = ''

    if df_current.empty:
        return df_current

    # Set up AI client: Gemini (default) → Claude (fallback)
    ai_client = None

    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_KEY and GEMINI_AVAILABLE:
        try:
            ai_client = {'type': 'gemini', 'client': genai.Client(api_key=GEMINI_KEY)}
            print(f"   🤖 Using Gemini: {GEMINI_MODEL}")
        except Exception as e:
            print(f"   ⚠️ Failed to configure Gemini: {e}")

    if not ai_client:
        ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
        if ANTHROPIC_KEY and CLAUDE_AVAILABLE:
            try:
                ai_client = {'type': 'claude', 'client': anthropic.Anthropic(api_key=ANTHROPIC_KEY)}
                print(f"   🤖 Using Claude: {CLAUDE_MODEL}")
            except Exception as e:
                print(f"   ⚠️ Failed to configure Claude: {e}")

    use_ai = ai_client is not None
    if not use_ai:
        print(f"   📊 No AI API key found - using statistical scoring only")

    # Convert history dates if needed
    if df_history is not None and len(df_history) > 0 and 'Date' in df_history.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_history['Date']):
            df_history = df_history.copy()
            df_history['Date'] = pd.to_datetime(df_history['Date'], errors='coerce')

    # Filter for items that need analysis
    items_to_score = df_current[
        (df_current['ai_deal_score'].isnull()) |
        (df_current['ai_deal_score'] == 0) |
        (df_current['ai_deal_score'] == 0.0)
    ]

    if items_to_score.empty:
        print(f"   ✅ All items already scored")
        return df_current

    print(f"   📝 Scoring {len(items_to_score)} items...")

    # Pre-compute context for all items
    context_cache = {}
    for idx, row in items_to_score.iterrows():
        item_name = row['Item']
        hist_ctx = get_historical_context(item_name, df_history) if df_history is not None else None
        cross_ctx = get_cross_store_context(item_name, df_current)
        context_cache[idx] = {'historical': hist_ctx, 'cross_store': cross_ctx}

    # Process in batches
    taxonomy_str = json.dumps(TAXONOMY, indent=2)
    total_batches = (len(items_to_score) + batch_size - 1) // batch_size

    for batch_num, i in enumerate(range(0, len(items_to_score), batch_size)):
        batch = items_to_score.iloc[i:i+batch_size]

        print(f"   📦 Batch {batch_num+1}/{total_batches} ({len(batch)} items)...", end=" ")

        # Build batch data with context
        batch_data = []
        batch_indices = []

        for idx, row in batch.iterrows():
            ctx = context_cache.get(idx, {})
            hist = ctx.get('historical')
            cross = ctx.get('cross_store')

            item_data = {
                'item': row['Item'],
                'price': row['Price_Value'],
                'store': row['Store'],
            }

            # v3.0: Include price_basis and unit_price
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
                    'num_stores': len(cross['stores'])
                }

            batch_data.append(item_data)
            batch_indices.append(idx)

        # Try AI API if available
        ai_results = None
        if use_ai and ai_client:
            ai_results = call_ai_api(batch_data, taxonomy_str, ai_client)

        # Process results
        if ai_results and len(ai_results) == len(batch_indices):
            print("✅")
            for idx, ai_result in zip(batch_indices, ai_results):
                df_current.at[idx, 'ai_category'] = ai_result.get('category', 'Other')
                df_current.at[idx, 'ai_sub_category'] = ai_result.get('subcategory', 'General')
                df_current.at[idx, 'ai_normalized_name'] = ai_result.get('normalized_name', '')
                df_current.at[idx, 'ai_deal_score'] = ai_result.get('score', 50)
                df_current.at[idx, 'ai_deal_rating'] = ai_result.get('rating', '😐 Fair')
                df_current.at[idx, 'ai_explanation'] = ai_result.get('explanation', '')
                df_current.at[idx, 'ai_confidence'] = ai_client['type']
        else:
            # Fallback to statistical scoring
            if use_ai:
                print("⚠️ Using statistical fallback")
            else:
                print("📊 Statistical scoring")

            for idx in batch_indices:
                row = df_current.loc[idx]
                ctx = context_cache.get(idx, {})
                hist = ctx.get('historical')
                cross = ctx.get('cross_store')

                # Compute statistical score (v3.0 aligned formula)
                score = compute_statistical_score(row['Price_Value'], hist, cross)
                explanation = generate_statistical_explanation(row['Price_Value'], hist, cross)
                rating = get_rating_from_score(score)
                category = categorize_by_keywords(row['Item'])

                df_current.at[idx, 'ai_category'] = category
                df_current.at[idx, 'ai_sub_category'] = 'General'
                df_current.at[idx, 'ai_normalized_name'] = row['Item']
                df_current.at[idx, 'ai_deal_score'] = score
                df_current.at[idx, 'ai_deal_rating'] = rating
                df_current.at[idx, 'ai_explanation'] = explanation
                df_current.at[idx, 'ai_confidence'] = 'statistical'

    # v3.2: Surface AI vs fallback split so silent rate-limit degradation
    # is visible. > 10% on statistical fallback usually means the API key
    # ran out of quota or the model is rate-limited; cross-store stats
    # downstream become unreliable when ai_normalized_name is the raw item.
    if 'ai_confidence' in df_current.columns:
        total = len(df_current)
        fb = (df_current['ai_confidence'] == 'statistical').sum()
        if total > 0:
            pct = fb / total * 100
            print(f"   📊 AI fallback rate: {fb:,}/{total:,} ({pct:.1f}%) on statistical scoring")
            if pct > 10:
                print(f"   ⚠️ ALERT: high statistical-fallback rate ({pct:.1f}%) - check API quota / rate limits")

    print(f"   ✅ Scoring complete")
    return df_current


if __name__ == "__main__":
    # Test with sample data
    print("AI Quality Analyzer v4.0 - Claude Edition")
    print(f"Claude Model: {CLAUDE_MODEL}  |  Gemini Model: {GEMINI_MODEL}")
    print(f"Claude Available: {CLAUDE_AVAILABLE}")

    # Check for API key
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        print(f"✓ API key found")
    else:
        print("⚠️ No ANTHROPIC_API_KEY in environment")