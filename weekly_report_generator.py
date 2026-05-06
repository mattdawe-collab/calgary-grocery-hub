"""
Calgary Grocery Hub - Weekly Social Media Report Generator v4.0

Uses Claude Sonnet for high-quality report writing.

Updates:
- v3.1: Per-100g pricing fix:
    * Applies per-100g corrections to current data on load
    * Cleans historical archive per-100g entries
    * get_deal_context() uses unit_price for per-100g items
    * Deal prices display as $/kg or $/lb for per-100g items
    * AI prompts include per-100g warnings
- v3.0: Initial release

Generates TWO reports:
1. STORE REPORT: Top deals organized by store, then category
2. CATEGORY REPORT: Top deals organized by category only

Key Features:
- Raw proteins only (excludes deli, prepared, frozen processed)
- Every deal includes context (% off average, lowest in X months, etc.)
- Honest assessments
"""

import pandas as pd
import numpy as np
import os
import json
import re
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Gemini SDK (default)
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ google-genai not installed")

# Claude SDK (fallback)
try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

# Per-100g correction (v3.1)
try:
    from get_deals import apply_per_100g_corrections, clean_archive_per_100g, is_likely_per_100g
    PER_100G_AVAILABLE = True
except ImportError:
    PER_100G_AVAILABLE = False
    print("⚠️ get_deals per-100g functions not available")

# =============================================================================
# CONFIGURATION
# =============================================================================

GEMINI_MODEL = "gemini-2.0-flash"
CLAUDE_MODEL = "claude-sonnet-4-6"
HISTORICAL_ARCHIVE = 'historical_archive.csv'
CURRENT_FLYERS = 'current_flyers.csv'

# Raw protein categories (what we consider "proteins")
RAW_PROTEIN_CATEGORIES = ['Pork', 'Poultry', 'Beef', 'Seafood', 'Lamb']

# Keywords that indicate PREPARED/PROCESSED meat (exclude these from "proteins")
PREPARED_MEAT_KEYWORDS = [
    'deli', 'sliced', 'lunch meat', 'sandwich', 'rotisserie', 'cooked',
    'smoked', 'cured', 'jerky', 'pepperoni', 'salami', 'prosciutto',
    'ham slice', 'turkey slice', 'chicken slice', 'roast beef slice',
    'nugget', 'finger', 'strip', 'tender', 'popcorn chicken', 'wing zing',
    'breaded', 'battered', 'frozen dinner', 'frozen entree', 'meal kit',
    'stuffed', 'marinated', 'seasoned', 'ready to eat', 'heat and serve',
    'corn dog', 'hot dog', 'wiener', 'frankfurter', 'bologna', 'mortadella',
    'pate', 'liverwurst', 'head cheese'
]

# Keywords that indicate RAW meat (include these)
RAW_MEAT_KEYWORDS = [
    'fresh', 'raw', 'uncooked', 'chop', 'steak', 'roast', 'tenderloin',
    'loin', 'rib', 'shoulder', 'leg', 'thigh', 'breast', 'drumstick',
    'wing', 'whole chicken', 'whole turkey', 'ground', 'mince',
    'fillet', 'filet', 'cutlet', 'scallopini', 'shank', 'osso buco',
    'brisket', 'flank', 'sirloin', 'ribeye', 'strip loin', 't-bone',
    'porterhouse', 'prime rib', 'chuck', 'round', 'rump',
    'salmon', 'trout', 'cod', 'halibut', 'tilapia', 'snapper', 'bass',
    'shrimp', 'prawn', 'scallop', 'mussel', 'clam', 'oyster', 'crab', 'lobster',
    'lamb chop', 'lamb leg', 'lamb shoulder', 'rack of lamb'
]

OTHER_CATEGORIES = ['Produce', 'Dairy & Eggs', 'Bakery', 'Pantry', 'Frozen', 'Snacks', 'Beverages']
FOOD_CATEGORIES = RAW_PROTEIN_CATEGORIES + OTHER_CATEGORIES

STORES = [
    'Real Canadian Superstore',
    'No Frills', 
    'Save-On-Foods',
    'Calgary Co-op',
    'Sobeys',
    'Safeway',
    'Walmart'
]

STORE_SHORT_NAMES = {
    'Real Canadian Superstore': 'Superstore',
    'No Frills': 'No Frills',
    'Save-On-Foods': 'Save-On',
    'Calgary Co-op': 'Co-op',
    'Sobeys': 'Sobeys',
    'Safeway': 'Safeway',
    'Walmart': 'Walmart'
}

CAT_EMOJI = {
    'Pork': '🐷', 'Poultry': '🐔', 'Beef': '🐄', 
    'Seafood': '🐟', 'Lamb': '🐑', 'Produce': '🥬',
    'Dairy & Eggs': '🧀', 'Bakery': '🍞', 'Pantry': '🥫',
    'Frozen': '❄️', 'Snacks': '🍿', 'Beverages': '🥤'
}


# =============================================================================
# DATA LOADING & FILTERING
# =============================================================================

def load_data():
    """Load current flyers and historical archive, applying per-100g corrections."""
    curr = pd.read_csv(CURRENT_FLYERS, low_memory=False)
    
    if os.path.exists(HISTORICAL_ARCHIVE):
        hist = pd.read_csv(HISTORICAL_ARCHIVE, low_memory=False)
        hist['Date'] = pd.to_datetime(hist['Date'], errors='coerce')
    else:
        hist = pd.DataFrame()
    
    # v3.1: Apply per-100g corrections
    if PER_100G_AVAILABLE:
        curr = apply_per_100g_corrections(curr)
        per_100g_count = curr.get('per_100g_corrected', pd.Series(dtype=bool)).sum()
        if per_100g_count > 0:
            print(f"   ✅ Corrected {per_100g_count} per-100g items in current data")
        
        if len(hist) > 0:
            # v3.2: report generator only needs the cleaned dataframe in
            # memory; the scraper already wrote any corrections to disk.
            # Three writers to historical_archive.csv per pipeline run was
            # asking for corruption.
            hist = clean_archive_per_100g(hist, save_to_disk=False)
    
    return curr, hist


def is_raw_protein(item_name: str, category: str) -> bool:
    """Check if item is a raw/unprocessed protein (not deli or prepared)."""
    if category not in RAW_PROTEIN_CATEGORIES:
        return False
    
    item_lower = item_name.lower()
    
    # Exclude prepared/processed items
    for keyword in PREPARED_MEAT_KEYWORDS:
        if keyword in item_lower:
            return False
    
    # Include if it has raw meat keywords OR doesn't have exclusion keywords
    for keyword in RAW_MEAT_KEYWORDS:
        if keyword in item_lower:
            return True
    
    # Default: include if in protein category and not explicitly excluded
    return True


def get_deal_context(item_name: str, price: float, hist_df: pd.DataFrame, 
                     curr_df: pd.DataFrame = None, row: pd.Series = None) -> dict:
    """
    Get comprehensive context for why this is a deal.
    
    v3.1: For per-100g items, compares unit_price ($/kg) against
    historical unit_price entries to avoid mixing per-100g with per-package.
    """
    context = {
        'has_context': False,
        'pct_below_avg': None,
        'is_lowest': False,
        'months_since_this_low': None,
        'historical_avg': None,
        'historical_min': None,
        'cross_store_best': None,
        'cross_store_savings': None,
        'context_text': '',
        'is_per_100g': False,
        'display_price': None,  # v3.1: real price to show (e.g. "$10.85/lb")
    }
    
    if hist_df is None or len(hist_df) == 0:
        return context
    
    # Ensure Date is datetime
    if 'Date' in hist_df.columns and not pd.api.types.is_datetime64_any_dtype(hist_df['Date']):
        hist_df = hist_df.copy()
        hist_df['Date'] = pd.to_datetime(hist_df['Date'], errors='coerce')
    
    # v3.1: Detect per-100g items and use unit_price for comparison
    is_per_100g = False
    compare_price = price
    
    if row is not None and row.get('per_100g_corrected', False):
        is_per_100g = True
        context['is_per_100g'] = True
        unit_price = row.get('unit_price')
        if pd.notna(unit_price) and unit_price > 0:
            compare_price = unit_price  # $/kg
            per_lb = unit_price * 0.453592
            context['display_price'] = f"${per_lb:.2f}/lb (${unit_price:.2f}/kg)"
    
    # Find matching historical items
    search_term = item_name[:25].lower()
    matches = hist_df[hist_df['Item'].str.lower().str.contains(search_term, na=False, regex=False)]
    
    # v3.1: For per-100g items, use unit_price from history (only compare like-for-like)
    if is_per_100g and 'unit_price' in matches.columns and 'price_basis' in matches.columns:
        per_100g_matches = matches[
            (matches['price_basis'] == 'per_100g') & 
            (matches['unit_price'].notna()) & 
            (matches['unit_price'] > 0)
        ]
        if len(per_100g_matches) >= 2:
            prices = per_100g_matches['unit_price'].dropna()
            prices = prices[prices > 0]
            matches_for_dates = per_100g_matches  # For date lookups
        else:
            # Not enough per-100g history — skip historical context entirely
            # to avoid mixing per-100g with per-package prices
            prices = pd.Series(dtype=float)
            matches_for_dates = matches
    else:
        prices = matches['Price_Value'].dropna()
        prices = prices[prices > 0]
        matches_for_dates = matches
    
    if len(prices) >= 3:
        avg = prices.mean()
        min_p = prices.min()
        max_p = prices.max()
        
        context['historical_avg'] = round(avg, 2)
        context['historical_min'] = round(min_p, 2)
        context['has_context'] = True
        
        # Calculate % below average
        if avg > 0:
            pct_below = ((avg - compare_price) / avg) * 100
            context['pct_below_avg'] = round(pct_below, 1)
        
        # Check if lowest
        if compare_price <= min_p:
            context['is_lowest'] = True
            
            # Find how long since this low
            if 'Date' in matches_for_dates.columns:
                price_col = 'unit_price' if is_per_100g and 'unit_price' in matches_for_dates.columns else 'Price_Value'
                low_matches = matches_for_dates[matches_for_dates[price_col] <= min_p + 0.01]
                if len(low_matches) > 0:
                    last_low = low_matches['Date'].max()
                    if pd.notna(last_low):
                        months_ago = (pd.Timestamp.now() - last_low).days / 30
                        context['months_since_this_low'] = round(months_ago, 1)
    
    # Cross-store comparison
    if curr_df is not None and len(curr_df) > 0:
        similar = curr_df[curr_df['Item'].str.lower().str.contains(search_term, na=False, regex=False)]
        if len(similar) > 1:
            # v3.1: For per-100g items, compare unit_price across stores
            if is_per_100g and 'unit_price' in similar.columns:
                similar_with_unit = similar[similar['unit_price'].notna() & (similar['unit_price'] > 0)]
                if len(similar_with_unit) > 1:
                    best_unit = similar_with_unit['unit_price'].min()
                    if compare_price <= best_unit:
                        context['cross_store_best'] = True
                    else:
                        context['cross_store_savings'] = round(compare_price - best_unit, 2)
            else:
                best_price = similar['Price_Value'].min()
                if price <= best_price:
                    context['cross_store_best'] = True
                else:
                    context['cross_store_savings'] = round(price - best_price, 2)
    
    # Build context text
    parts = []
    if context['is_per_100g'] and context['display_price']:
        parts.append(f"Price is per 100g → real price {context['display_price']}")
    
    if context['is_lowest']:
        if context['months_since_this_low'] and context['months_since_this_low'] > 1:
            parts.append(f"LOWEST in {context['months_since_this_low']:.0f} months!")
        else:
            parts.append("LOWEST PRICE!")
    elif context['pct_below_avg'] and context['pct_below_avg'] > 5:
        parts.append(f"{context['pct_below_avg']:.0f}% below avg ${context['historical_avg']:.2f}")
    elif context['pct_below_avg'] and context['pct_below_avg'] < -5:
        parts.append(f"Above avg (usually ${context['historical_avg']:.2f})")
    
    if context['cross_store_best'] and not context['is_per_100g']:
        parts.append("Best price across stores")
    
    context['context_text'] = " | ".join(parts) if parts else ""
    
    return context


# =============================================================================
# REPORT DATA PREPARATION
# =============================================================================

def prepare_report_data(curr_df: pd.DataFrame, hist_df: pd.DataFrame) -> dict:
    """Prepare comprehensive data for both reports."""
    
    # Ensure dates are datetime
    if hist_df is not None and len(hist_df) > 0 and 'Date' in hist_df.columns:
        if not pd.api.types.is_datetime64_any_dtype(hist_df['Date']):
            hist_df = hist_df.copy()
            hist_df['Date'] = pd.to_datetime(hist_df['Date'], errors='coerce')
    
    # Get date range. Coerce first because Valid_Until can be a mix of
    # ISO strings and Timestamps after the v3.2 archive backfill, and
    # `.max()` on mixed types raises TypeError.
    if 'Valid_Until' in curr_df.columns:
        _vu = pd.to_datetime(curr_df['Valid_Until'], errors='coerce')
        _vu_max = _vu.max()
        valid_until = _vu_max.strftime('%Y-%m-%d') if pd.notna(_vu_max) else None
    else:
        valid_until = None

    # Determine score column (v3.1: prefer deal_score from v3.0+)
    if 'deal_score' in curr_df.columns:
        score_col = 'deal_score'
    elif 'ai_deal_score' in curr_df.columns:
        score_col = 'ai_deal_score'
    elif 'Context_Score' in curr_df.columns:
        score_col = 'Context_Score'
    else:
        score_col = 'deal_score'
        curr_df[score_col] = 50
    
    cat_col = 'ai_category' if 'ai_category' in curr_df.columns else None
    
    report_data = {
        'week_ending': valid_until if valid_until else datetime.now().strftime('%Y-%m-%d'),
        'total_deals': len(curr_df),
        'score_col': score_col,
        'proteins': {},      # Raw proteins only
        'categories': {},    # Other categories
        'stores': {},        # Store-by-store data
        'top_deals': [],     # Overall top deals
    }
    
    # === RAW PROTEINS ===
    for cat in RAW_PROTEIN_CATEGORIES:
        if not cat_col:
            continue
        
        cat_items = curr_df[curr_df[cat_col] == cat].copy()
        
        # Filter to raw proteins only
        raw_items = []
        for idx, row in cat_items.iterrows():
            if is_raw_protein(row['Item'], cat):
                raw_items.append(idx)
        
        cat_items = cat_items.loc[raw_items] if raw_items else pd.DataFrame()
        
        if len(cat_items) == 0:
            continue
        
        deals = []
        for _, row in cat_items.iterrows():
            ctx = get_deal_context(row['Item'], row['Price_Value'], hist_df, curr_df, row=row)
            
            # v3.1: Build display price for per-100g items
            display_price = row['Price_Value']
            price_note = ''
            if row.get('per_100g_corrected', False):
                unit_price = row.get('unit_price', 0)
                if pd.notna(unit_price) and unit_price > 0:
                    per_lb = unit_price * 0.453592
                    display_price = per_lb  # Show per-lb for consistency
                    price_note = f'(${row["Price_Value"]:.2f}/100g = ${per_lb:.2f}/lb)'
            
            deals.append({
                'item': row['Item'][:60],
                'price': display_price,
                'raw_price': row['Price_Value'],
                'store': STORE_SHORT_NAMES.get(row['Store'], row['Store']),
                'score': row[score_col] if pd.notna(row[score_col]) else 50,
                'context': ctx,
                'is_per_100g': bool(row.get('per_100g_corrected', False)),
                'price_note': price_note
            })
        
        deals.sort(key=lambda x: x['score'], reverse=True)
        avg_score = cat_items[score_col].mean() if len(cat_items) > 0 else 50
        
        report_data['proteins'][cat] = {
            'count': len(cat_items),
            'avg_score': round(avg_score, 0) if pd.notna(avg_score) else 50,
            'deals': deals
        }
    
    # === OTHER CATEGORIES ===
    for cat in OTHER_CATEGORIES:
        if not cat_col:
            continue
        
        cat_items = curr_df[curr_df[cat_col] == cat].copy()
        if len(cat_items) == 0:
            continue
        
        deals = []
        for _, row in cat_items.nlargest(10, score_col).iterrows():
            ctx = get_deal_context(row['Item'], row['Price_Value'], hist_df, curr_df, row=row)
            
            # v3.1: Display price for per-100g items
            display_price = row['Price_Value']
            price_note = ''
            if row.get('per_100g_corrected', False):
                unit_price = row.get('unit_price', 0)
                if pd.notna(unit_price) and unit_price > 0:
                    per_lb = unit_price * 0.453592
                    display_price = per_lb
                    price_note = f'(${row["Price_Value"]:.2f}/100g = ${per_lb:.2f}/lb)'
            
            deals.append({
                'item': row['Item'][:60],
                'price': display_price,
                'raw_price': row['Price_Value'],
                'store': STORE_SHORT_NAMES.get(row['Store'], row['Store']),
                'score': row[score_col] if pd.notna(row[score_col]) else 50,
                'context': ctx,
                'is_per_100g': bool(row.get('per_100g_corrected', False)),
                'price_note': price_note
            })
        
        deals.sort(key=lambda x: x['score'], reverse=True)
        avg_score = cat_items[score_col].mean() if len(cat_items) > 0 else 50
        
        report_data['categories'][cat] = {
            'count': len(cat_items),
            'avg_score': round(avg_score, 0) if pd.notna(avg_score) else 50,
            'deals': deals
        }
    
    # === STORE-BY-STORE ===
    for store in STORES:
        store_items = curr_df[curr_df['Store'] == store].copy()
        if len(store_items) == 0:
            continue
        
        short_name = STORE_SHORT_NAMES.get(store, store)
        
        # Filter to food
        if cat_col:
            food_items = store_items[store_items[cat_col].isin(FOOD_CATEGORIES)]
        else:
            food_items = store_items
        
        avg_score = food_items[score_col].mean() if len(food_items) > 0 else 50
        
        store_data = {
            'total_deals': len(food_items),
            'avg_score': round(avg_score, 0) if pd.notna(avg_score) else 50,
            'categories': {}
        }
        
        # Get top deals per category for this store
        all_cats = RAW_PROTEIN_CATEGORIES + OTHER_CATEGORIES
        for cat in all_cats:
            if not cat_col:
                continue
            
            cat_items = store_items[store_items[cat_col] == cat]
            
            # For proteins, filter to raw only
            if cat in RAW_PROTEIN_CATEGORIES:
                raw_idx = [idx for idx, row in cat_items.iterrows() if is_raw_protein(row['Item'], cat)]
                cat_items = cat_items.loc[raw_idx] if raw_idx else pd.DataFrame()
            
            if len(cat_items) == 0:
                continue
            
            top_deals = []
            for _, row in cat_items.nlargest(3, score_col).iterrows():
                ctx = get_deal_context(row['Item'], row['Price_Value'], hist_df, curr_df, row=row)
                
                # v3.1: Display price for per-100g items
                display_price = row['Price_Value']
                price_note = ''
                if row.get('per_100g_corrected', False):
                    unit_price = row.get('unit_price', 0)
                    if pd.notna(unit_price) and unit_price > 0:
                        per_lb = unit_price * 0.453592
                        display_price = per_lb
                        price_note = f'(${row["Price_Value"]:.2f}/100g = ${per_lb:.2f}/lb)'
                
                top_deals.append({
                    'item': row['Item'][:45],
                    'price': display_price,
                    'raw_price': row['Price_Value'],
                    'score': row[score_col] if pd.notna(row[score_col]) else 50,
                    'context': ctx,
                    'is_per_100g': bool(row.get('per_100g_corrected', False)),
                    'price_note': price_note
                })
            
            cat_avg = cat_items[score_col].mean() if len(cat_items) > 0 else 50
            
            store_data['categories'][cat] = {
                'count': len(cat_items),
                'avg_score': round(cat_avg, 0) if pd.notna(cat_avg) else 50,
                'deals': top_deals
            }
        
        report_data['stores'][short_name] = store_data
    
    return report_data


# =============================================================================
# REPORT 1: BY STORE (with full context)
# =============================================================================

def generate_store_report(report_data: dict, use_ai: bool = True) -> str:
    """Generate report organized by store, then category."""

    if use_ai:
        result = generate_store_report_ai(report_data)
        if result:
            return result
    return generate_store_report_template(report_data)


def _get_store_report_prompt(report_data: dict) -> str:
    """Build the prompt for store-focused report."""
    return f"""You are a Calgary grocery deals expert writing a weekly social media post.
Your audience is budget-conscious families planning their shopping trips STORE BY STORE.

CRITICAL RULES:
1. EVERY deal MUST include WHY it's a deal (e.g., "25% below avg", "lowest in 4 months")
2. "Proteins" means RAW MEAT ONLY - no deli, no prepared foods
3. Be honest - if a store has weak deals, say so
4. Keep it scannable with emojis and clear sections
5. ⚠️ PER-100G ITEMS: Some items have "is_per_100g": true. These are fresh counter items
   priced per 100g (e.g., $2.39/100g ≈ $10.85/lb). The "price" field already shows the
   converted per-lb price. The "price_note" explains the conversion. ALWAYS show the per-lb
   price for these items (not the misleading per-100g price). If the deal score is below 60,
   do NOT feature it as a top deal — it's an average price, not a bargain.

STRUCTURE:
1. 🛒 Catchy headline with week ending date
2. For EACH STORE (in order of best deals):
   📍 STORE NAME
   Overall: X deals, score assessment

   🥩 RAW PROTEINS:
   • $X.XX Item Name - [context: why it's a deal]

   🥬 PRODUCE:
   • $X.XX Item - [context]

   [Continue for each category with deals]

   💡 VERDICT: One sentence on when to shop here

3. 📝 BOTTOM LINE: Which stores to hit this week and why

DATA:
{json.dumps(report_data, indent=2, default=str)}

Write a complete, engaging social media post (~2500-3500 chars).
End with: #YYCDeals #CalgaryGrocery #GroceryDeals"""


def generate_store_report_ai(report_data: dict) -> str:
    """Use Gemini (default) or Claude (fallback) to write store-focused report."""

    prompt = _get_store_report_prompt(report_data)

    # Try Gemini first
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_KEY and GEMINI_AVAILABLE:
        try:
            client = genai.Client(api_key=GEMINI_KEY)
            print(f"   Using model: {GEMINI_MODEL}")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.8,
                )
            )
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")

    # Fallback to Claude
    ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
    if ANTHROPIC_KEY and CLAUDE_AVAILABLE:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            print(f"   Using model: {CLAUDE_MODEL}")
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                temperature=0.8,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"⚠️ Claude API error: {e}")

    return None


def generate_store_report_template(report_data: dict) -> str:
    """Template-based store report."""
    lines = []
    
    lines.append(f"🛒 CALGARY GROCERY DEALS BY STORE - Week Ending {report_data['week_ending']}")
    lines.append("")
    lines.append("Plan your shopping trip! Here's what's worth grabbing at each store 👇")
    lines.append("")
    
    # Sort stores by avg score
    sorted_stores = sorted(
        report_data['stores'].items(),
        key=lambda x: x[1]['avg_score'],
        reverse=True
    )
    
    for store_name, store_data in sorted_stores:
        lines.append("━" * 40)
        lines.append(f"📍 {store_name.upper()}")
        
        avg = store_data['avg_score']
        if avg >= 75:
            verdict = "🔥 Hot this week!"
        elif avg >= 65:
            verdict = "✓ Solid deals"
        else:
            verdict = "😐 Average week"
        
        lines.append(f"{store_data['total_deals']} deals | {verdict}")
        lines.append("")
        
        # Proteins first
        for cat in RAW_PROTEIN_CATEGORIES:
            if cat not in store_data['categories']:
                continue
            cat_data = store_data['categories'][cat]
            if not cat_data['deals']:
                continue
            
            emoji = CAT_EMOJI.get(cat, '🍖')
            lines.append(f"{emoji} {cat.upper()}:")
            
            for deal in cat_data['deals'][:2]:
                ctx = deal['context']
                ctx_text = f" - {ctx['context_text']}" if ctx['context_text'] else ""
                # v3.1: Show per-lb price for per-100g items
                if deal.get('is_per_100g') and deal.get('price_note'):
                    lines.append(f"  • {deal['item'][:30]} {deal['price_note']}")
                    if ctx_text:
                        lines.append(f"    ↳{ctx_text}")
                else:
                    lines.append(f"  • ${deal['price']:.2f} {deal['item'][:30]}{ctx_text}")
            lines.append("")
        
        # Other categories
        for cat in OTHER_CATEGORIES:
            if cat not in store_data['categories']:
                continue
            cat_data = store_data['categories'][cat]
            if not cat_data['deals']:
                continue
            
            emoji = CAT_EMOJI.get(cat, '📦')
            top = cat_data['deals'][0]
            ctx = top['context']
            # v3.1: Handle per-100g items
            if top.get('is_per_100g') and top.get('price_note'):
                lines.append(f"{emoji} {cat}: {top['item'][:25]} {top['price_note']}")
            else:
                ctx_text = f" - {ctx['context_text']}" if ctx['context_text'] else ""
                lines.append(f"{emoji} {cat}: ${top['price']:.2f} {top['item'][:25]}{ctx_text}")
        
        lines.append("")
    
    lines.append("━" * 40)
    lines.append("")
    lines.append("#YYCDeals #CalgaryGrocery #GroceryDeals #MealPlanning")
    
    return "\n".join(lines)


# =============================================================================
# REPORT 2: BY CATEGORY (simpler, top deals focus)
# =============================================================================

def generate_category_report(report_data: dict, use_ai: bool = True) -> str:
    """Generate report organized by category."""

    if use_ai:
        result = generate_category_report_ai(report_data)
        if result:
            return result
    return generate_category_report_template(report_data)


def _get_category_report_prompt(report_data: dict) -> str:
    """Build the prompt for category-focused report."""
    return f"""You are a Calgary grocery deals expert writing a weekly social media post.
Your audience wants to know the BEST DEALS BY CATEGORY regardless of store.

CRITICAL RULES:
1. EVERY deal MUST include context (e.g., "25% off", "lowest since October")
2. "Proteins" = RAW UNPROCESSED MEAT ONLY (no deli, nuggets, prepared)
3. Lead with PROTEINS - this is what meal planners care about most
4. Be specific with prices and store names
5. ⚠️ PER-100G ITEMS: Some items have "is_per_100g": true. These are fresh counter items
   priced per 100g (e.g., $2.39/100g ≈ $10.85/lb). The "price" field already shows the
   converted per-lb price. ALWAYS show the per-lb price. If the deal score is below 60,
   do NOT feature it as a top deal — it's an average price, not a bargain.

STRUCTURE:
1. 🛒 Catchy headline

2. 🥩 RAW PROTEIN DEALS (the main event!)
   🐷 PORK: Overall assessment
   • $X.XX Item @ Store - [why it's a deal]
   • $X.XX Item @ Store - [why it's a deal]

   🐔 CHICKEN: Overall assessment
   [etc for Beef, Seafood, Lamb]

3. 🛒 OTHER TOP DEALS
   🥬 Produce: Top 2-3 deals with context
   🧀 Dairy: Top deals
   [etc]

4. 📝 THIS WEEK'S WINNERS
   - Best protein to stock up on
   - Best overall value category
   - What to skip/wait on

DATA:
{json.dumps(report_data, indent=2, default=str)}

Write engaging social media post (~2000-3000 chars).
End with: #YYCDeals #CalgaryGrocery #MealPrep"""


def generate_category_report_ai(report_data: dict) -> str:
    """Use Gemini (default) or Claude (fallback) to write category-focused report."""

    prompt = _get_category_report_prompt(report_data)

    # Try Gemini first
    GEMINI_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_KEY and GEMINI_AVAILABLE:
        try:
            client = genai.Client(api_key=GEMINI_KEY)
            print(f"   Using model: {GEMINI_MODEL}")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.8,
                )
            )
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")

    # Fallback to Claude
    ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
    if ANTHROPIC_KEY and CLAUDE_AVAILABLE:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            print(f"   Using model: {CLAUDE_MODEL}")
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=8192,
                temperature=0.8,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"⚠️ Claude API error: {e}")

    return None


def generate_category_report_template(report_data: dict) -> str:
    """Template-based category report."""
    lines = []
    
    lines.append(f"🛒 CALGARY TOP DEALS - Week Ending {report_data['week_ending']}")
    lines.append("")
    lines.append("This week's best grocery deals by category! 👇")
    lines.append("")
    
    # === PROTEINS ===
    lines.append("━" * 40)
    lines.append("🥩 RAW PROTEIN DEALS")
    lines.append("━" * 40)
    
    for cat in RAW_PROTEIN_CATEGORIES:
        if cat not in report_data['proteins']:
            continue
        
        data = report_data['proteins'][cat]
        if not data['deals']:
            continue
        
        emoji = CAT_EMOJI.get(cat, '🍖')
        avg = data['avg_score']
        
        if avg >= 80:
            assessment = "🔥 Great week!"
        elif avg >= 70:
            assessment = "✓ Decent"
        else:
            assessment = "😐 Average"
        
        lines.append("")
        lines.append(f"{emoji} {cat.upper()} - {assessment}")
        
        for deal in data['deals'][:3]:
            ctx = deal['context']
            # v3.1: Show per-lb price for per-100g items
            if deal.get('is_per_100g') and deal.get('price_note'):
                lines.append(f"  • {deal['item'][:30]} @ {deal['store']}")
                lines.append(f"    ↳ {deal['price_note']}")
                if ctx['context_text']:
                    lines.append(f"    ↳ {ctx['context_text']}")
            elif ctx['context_text']:
                lines.append(f"  • ${deal['price']:.2f} {deal['item'][:30]} @ {deal['store']}")
                lines.append(f"    ↳ {ctx['context_text']}")
            else:
                lines.append(f"  • ${deal['price']:.2f} {deal['item'][:30]} @ {deal['store']}")
    
    # === OTHER CATEGORIES ===
    lines.append("")
    lines.append("━" * 40)
    lines.append("🛒 OTHER TOP DEALS")
    lines.append("━" * 40)
    
    for cat in OTHER_CATEGORIES:
        if cat not in report_data['categories']:
            continue
        
        data = report_data['categories'][cat]
        if not data['deals']:
            continue
        
        emoji = CAT_EMOJI.get(cat, '📦')
        lines.append("")
        lines.append(f"{emoji} {cat.upper()}:")
        
        for deal in data['deals'][:2]:
            ctx = deal['context']
            # v3.1: Show per-lb price for per-100g items
            if deal.get('is_per_100g') and deal.get('price_note'):
                lines.append(f"  • {deal['item'][:28]} @ {deal['store']} {deal['price_note']}")
            else:
                ctx_text = f" - {ctx['context_text']}" if ctx['context_text'] else ""
                lines.append(f"  • ${deal['price']:.2f} {deal['item'][:28]} @ {deal['store']}{ctx_text}")
    
    # === BOTTOM LINE ===
    lines.append("")
    lines.append("━" * 40)
    lines.append("📝 THIS WEEK'S WINNERS")
    lines.append("━" * 40)
    
    # Find best protein category
    if report_data['proteins']:
        best_protein = max(report_data['proteins'].items(), key=lambda x: x[1]['avg_score'])
        lines.append(f"🥩 Stock up on: {best_protein[0]}")
    
    # Find best overall category
    all_cats = {**report_data['proteins'], **report_data['categories']}
    if all_cats:
        best_cat = max(all_cats.items(), key=lambda x: x[1]['avg_score'])
        lines.append(f"🏆 Best value: {best_cat[0]}")
    
    lines.append("")
    lines.append("#YYCDeals #CalgaryGrocery #MealPrep #BudgetMeals")
    
    return "\n".join(lines)


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def generate_weekly_reports(use_ai: bool = True):
    """Generate both weekly reports."""
    
    print("=" * 60)
    print("🛒 CALGARY GROCERY HUB - WEEKLY REPORT GENERATOR v3.1")
    print("=" * 60)
    print()
    
    print("📂 Loading data...")
    curr, hist = load_data()
    print(f"   Current deals: {len(curr)}")
    print(f"   Historical records: {len(hist)}")
    
    print("\n📊 Preparing report data...")
    report_data = prepare_report_data(curr, hist)
    print(f"   Raw protein categories: {len(report_data['proteins'])}")
    print(f"   Other categories: {len(report_data['categories'])}")
    print(f"   Stores: {len(report_data['stores'])}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Output directory
    output_dir = os.path.dirname(os.path.abspath(__file__))
    
    # === REPORT 1: BY STORE ===
    print(f"\n✍️ Generating STORE report...")
    store_report = generate_store_report(report_data, use_ai=use_ai)
    
    store_filename = os.path.join(output_dir, f"weekly_report_STORES_{timestamp}.txt")
    with open(store_filename, 'w', encoding='utf-8') as f:
        f.write(store_report)
    print(f"   ✅ Saved: {store_filename}")
    
    # === REPORT 2: BY CATEGORY ===
    print(f"\n✍️ Generating CATEGORY report...")
    category_report = generate_category_report(report_data, use_ai=use_ai)
    
    category_filename = os.path.join(output_dir, f"weekly_report_CATEGORIES_{timestamp}.txt")
    with open(category_filename, 'w', encoding='utf-8') as f:
        f.write(category_report)
    print(f"   ✅ Saved: {category_filename}")
    
    # === PREVIEW ===
    print("\n" + "=" * 60)
    print("STORE REPORT PREVIEW:")
    print("=" * 60)
    print(store_report[:2000])
    if len(store_report) > 2000:
        print("\n... [truncated] ...")
    
    print("\n" + "=" * 60)
    print("CATEGORY REPORT PREVIEW:")
    print("=" * 60)
    print(category_report[:2000])
    if len(category_report) > 2000:
        print("\n... [truncated] ...")
    
    return store_report, category_report


if __name__ == "__main__":
    import sys
    use_ai = "--no-ai" not in sys.argv
    
    generate_weekly_reports(use_ai=use_ai)