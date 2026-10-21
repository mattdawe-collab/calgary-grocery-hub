"""
Calgary Grocery Hub - Weekly Social Media Report Generator v5.0

Writes the weekly posts with the local Claude Code CLI (Opus by default).

Updates:
- v5.0: Claude Code CLI backend (see ai_backends.py); Gemini kept as opt-in
    * Rejects truncated AI output (Gemini thinking-token bug, Jun-Sep 2026)
    * Week-ending date = most common flyer end date, not a long-flyer outlier
    * Adds a short Facebook-ready post and weekly_reports_latest.json for the
      public "This Week" web page
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
import sys
import json
import re
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from data_quality import (
    add_quality_metadata,
    parse_dates,
    filter_grocery_relevant,
    repair_category,
    sanitize_unit_prices,
)
from deal_guidance import add_deal_guidance
from ai_backends import (
    ClaudeCLIError,
    anthropic_model,
    claude_cli_model,
    response_text,
    run_claude_cli,
    select_backend,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path, override=True)

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

GEMINI_MODEL = os.getenv("GEMINI_REPORT_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
CLAUDE_MODEL = os.getenv("CLAUDE_REPORT_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
HISTORICAL_ARCHIVE = 'historical_archive.csv'
CURRENT_FLYERS = 'current_flyers.csv'
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')
LATEST_JSON = 'weekly_reports_latest.json'
MIN_REPORT_CHARS = 800

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
    'taco kit',
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
    curr, excluded = filter_grocery_relevant(curr)
    if len(excluded) > 0:
        print(f"   🚫 Excluded {len(excluded)} non-grocery/general-merchandise rows from reports")
    curr, unit_issue_count = sanitize_unit_prices(curr)
    if unit_issue_count:
        print(f"   ⚠️ Cleared {unit_issue_count} suspicious unit prices for reports")
    categories = curr.apply(
        lambda row: repair_category(row.get('Item', ''), row.get('ai_category', 'Other')),
        axis=1,
        result_type='expand',
    )
    curr['display_category'] = categories[0]
    curr['category_source'] = categories[1]
    curr = add_quality_metadata(curr)
    curr = add_deal_guidance(curr)
    
    if os.path.exists(HISTORICAL_ARCHIVE):
        hist = pd.read_csv(HISTORICAL_ARCHIVE, low_memory=False)
        hist['Date'] = parse_dates(hist['Date'])
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
        hist_df['Date'] = parse_dates(hist_df['Date'])
    
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
            hist_df['Date'] = parse_dates(hist_df['Date'])
    
    valid_until = _week_ending(curr_df)

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
    
    cat_col = 'display_category' if 'display_category' in curr_df.columns else (
        'ai_category' if 'ai_category' in curr_df.columns else None
    )
    
    report_data = {
        'week_ending': valid_until,
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



def _week_ending(curr_df: pd.DataFrame) -> str:
    """Most common flyer end date (YYYY-MM-DD).

    Using max() picked up a single long-running Walmart flyer and labelled a
    September post "Week Ending October 21". The modal date is what shoppers
    mean by "this week".

    Parsing goes through parse_dates, not utc=True: Flipp sends
    "2026-09-30T23:59:59-04:00" and converting that to UTC rolls it to Oct 1,
    which told shoppers the deals ran a day longer than they did.
    """
    if 'Valid_Until' in curr_df.columns:
        vu = parse_dates(curr_df['Valid_Until']).dropna()
        if len(vu):
            days = vu.dt.strftime('%Y-%m-%d')
            return days.mode().iloc[0]
    return datetime.now().strftime('%Y-%m-%d')



_PREAMBLE_RE = re.compile(r"^(here('s| is| are)\b.*?:|sure[,!].*?:|okay[,!].*?:)\s*$", re.IGNORECASE)


def _clean_ai_post(text):
    """Trim model chatter around a social post.

    Models sometimes prepend "Here's your post:" and append a "---\nNotes:"
    block after the hashtags. Keep only the post: drop leading preamble lines,
    cut everything after the last hashtag line, and strip markdown bold, which
    Facebook and Telegram render literally.
    """
    if not text or not isinstance(text, str):
        return text
    lines = text.replace("\r\n", "\n").strip().split("\n")
    while lines and (not lines[0].strip() or _PREAMBLE_RE.match(lines[0].strip())):
        lines.pop(0)
    last_tag = None
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            last_tag = i
    if last_tag is not None:
        lines = lines[: last_tag + 1]
    cleaned = "\n".join(lines).replace("**", "").strip()
    return cleaned

def _report_looks_complete(text, min_chars: int = MIN_REPORT_CHARS) -> bool:
    """Reject truncated or empty model output so it never gets published."""
    if not text or not isinstance(text, str):
        return False
    body = text.strip()
    if len(body) < min_chars:
        return False
    return '#' in body[-200:]


def _anthropic_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _generate_text_with_ai(prompt: str, kind: str = "report", temperature: float = 0.8,
                           cache_prefix: str | None = None):
    """Run a narrative prompt on the selected backend. Returns text or None.

    `cache_prefix` is content that is byte-identical across calls - the week's
    report data is the same for the store report, the category report and the
    Facebook post. Sending it as its own cached block means only the first of
    the three pays full price for those ~84k tokens.
    """
    backend = select_backend(verbose=True)['type']

    if backend == 'claude_code':
        model = claude_cli_model(kind)
        print(f"   Using Claude Code CLI: {model}")
        try:
            full = f"{cache_prefix}\n\n{prompt}" if cache_prefix else prompt
            return run_claude_cli(full, model=model)
        except ClaudeCLIError as e:
            print(f"⚠️ Claude CLI error: {e}")
            return None

    if backend == 'anthropic' and CLAUDE_AVAILABLE:
        model = anthropic_model(kind)
        print(f"   Using Claude API: {model}")
        try:
            if cache_prefix:
                content = [
                    {"type": "text", "text": cache_prefix,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": prompt},
                ]
            else:
                content = prompt
            # No temperature: current models reject sampling parameters.
            # The argument is kept for the CLI path and older models.
            response = _anthropic_client().messages.create(
                model=model,
                max_tokens=16000,
                messages=[{"role": "user", "content": content}],
            )
            usage = getattr(response, "usage", None)
            if usage is not None and getattr(usage, "cache_read_input_tokens", 0):
                print(f"   ✓ cache hit: {usage.cache_read_input_tokens:,} tokens reused")
            return response_text(response)
        except Exception as e:
            print(f"⚠️ Claude API error: {e}")
            return None

    if backend == 'gemini' and GEMINI_AVAILABLE:
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            print(f"   Using model: {GEMINI_MODEL}")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=16384,
                    temperature=temperature,
                    # Thinking tokens share the output budget; cap them so the
                    # post itself is never cut off.
                    thinking_config=genai.types.ThinkingConfig(thinking_budget=1024),
                ),
            )
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")
            return None

    return None


# =============================================================================
# REPORT 1: BY STORE (with full context)
# =============================================================================

def generate_store_report(report_data: dict, use_ai: bool = True) -> str:
    """Generate report organized by store, then category."""

    if use_ai:
        result = _clean_ai_post(generate_store_report_ai(report_data))
        if _report_looks_complete(result):
            return result.strip()
        if result:
            print("   ⚠️ AI store report looked truncated/incomplete - using template instead")
    return generate_store_report_template(report_data)



def _report_data_block(report_data: dict) -> str:
    """The week's data, rendered identically for every report.

    All three reports read the same figures, so this is sent as one cached
    block and the instructions differ after it. sort_keys keeps the bytes
    stable between calls - any drift silently costs a cache miss.
    """
    return "DATA:\n" + json.dumps(report_data, indent=2, default=str, sort_keys=True)


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

Write a complete, engaging social media post (~2500-3500 chars) from the DATA above.
Plain text only: no markdown bold/headers, Facebook shows the asterisks literally.
Output ONLY the post. No preamble, no notes, no commentary, no questions.
The week-ending date comes from the flyer data; use it as given, never remark on today's date.
End with: #YYCDeals #CalgaryGrocery #GroceryDeals"""


def generate_store_report_ai(report_data: dict) -> str:
    """Write the store-focused report with the configured AI backend."""
    return _generate_text_with_ai(
        _get_store_report_prompt(report_data), kind="report",
        cache_prefix=_report_data_block(report_data),
    )


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
        result = _clean_ai_post(generate_category_report_ai(report_data))
        if _report_looks_complete(result):
            return result.strip()
        if result:
            print("   ⚠️ AI category report looked truncated/incomplete - using template instead")
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

Write engaging social media post (~2000-3000 chars) from the DATA above.
Plain text only: no markdown bold/headers, Facebook shows the asterisks literally.
Output ONLY the post. No preamble, no notes, no commentary, no questions.
The week-ending date comes from the flyer data; use it as given, never remark on today's date.
End with: #YYCDeals #CalgaryGrocery #MealPrep"""


def generate_category_report_ai(report_data: dict) -> str:
    """Write the category-focused report with the configured AI backend."""
    return _generate_text_with_ai(
        _get_category_report_prompt(report_data), kind="report",
        cache_prefix=_report_data_block(report_data),
    )


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


# =============================================================================
# REPORT 3: SHORT FACEBOOK POST (links to the public weekly page)
# =============================================================================

FACEBOOK_MAX_CHARS = 2000


def _top_deals_for_post(report_data: dict, limit: int = 8) -> list:
    picks = []
    for cat in RAW_PROTEIN_CATEGORIES:
        for deal in report_data.get('proteins', {}).get(cat, {}).get('deals', [])[:2]:
            picks.append((cat, deal))
    for cat in OTHER_CATEGORIES:
        for deal in report_data.get('categories', {}).get(cat, {}).get('deals', [])[:1]:
            picks.append((cat, deal))
    picks.sort(key=lambda x: x[1].get('score', 0), reverse=True)
    return picks[:limit]


def _facebook_post_template(report_data: dict, page_url: str) -> str:
    lines = [f"🛒 Calgary grocery deals - week ending {report_data['week_ending']}", ""]
    for cat, deal in _top_deals_for_post(report_data):
        ctx = (deal.get('context') or {}).get('context_text') or ''
        ctx_text = f" ({ctx})" if ctx else ""
        store = deal.get('store', '')
        at = f" @ {store}" if store else ""
        lines.append(f"{CAT_EMOJI.get(cat, '•')} ${deal['price']:.2f} {deal['item'][:40]}{at}{ctx_text}")
    lines += ["", "Full store-by-store breakdown, with price history for every deal:", page_url, "",
              "#YYCDeals #CalgaryGrocery"]
    text = "\n".join(lines)
    if len(text) > FACEBOOK_MAX_CHARS:
        text = text[:FACEBOOK_MAX_CHARS - len(page_url) - 30].rsplit("\n", 1)[0] + f"\n\nFull list: {page_url}"
    return text


def _get_facebook_post_prompt(report_data: dict, page_url: str) -> str:
    picks = [
        {"category": cat, "item": d['item'], "price": round(float(d['price']), 2), "store": d.get('store', ''),
         "why": (d.get('context') or {}).get('context_text', '')}
        for cat, d in _top_deals_for_post(report_data, limit=10)
    ]
    return f"""Write a short Facebook post for a Calgary grocery deals group.

Week ending: {report_data['week_ending']}
Use only these deals, with the prices and stores exactly as given in the DATA
above; these are the ones to feature, in this order of preference:
{json.dumps([p['item'] for p in picks], indent=2)}

RULES:
- Plain text, no markdown, under 1500 characters TOTAL.
- Friendly, practical, no hype. One short intro line.
- List 6-8 deals as "$price item @ store - why" lines with a category emoji.
- Do not invent deals, prices or dates. Do not mention Telegram.
- Use the week-ending date as given; never remark on today's date.
- Output ONLY the post: no preamble, no notes, no commentary after the hashtags.
- End with exactly these two lines:
{page_url}
#YYCDeals #CalgaryGrocery"""


def generate_facebook_post(report_data: dict, page_url: str, use_ai: bool = True) -> str:
    """Copy-paste-ready Facebook post that links to the public weekly page."""
    if use_ai:
        text = _clean_ai_post(_generate_text_with_ai(
            _get_facebook_post_prompt(report_data, page_url), kind="report",
            temperature=0.7, cache_prefix=_report_data_block(report_data),
        ))
        if text and text.strip():
            text = text.strip()
            if page_url not in text:
                text = f"{text}\n\n{page_url}"
            if len(text) <= FACEBOOK_MAX_CHARS:
                return text
            print("   ⚠️ AI Facebook post too long - using template instead")
    return _facebook_post_template(report_data, page_url)


def _public_page_url() -> str:
    base = (os.getenv("PUBLIC_DASHBOARD_URL") or os.getenv("DASHBOARD_PUBLIC_URL") or "").strip().rstrip("/")
    return f"{base}/" if base else ""


def generate_weekly_reports(use_ai: bool = True):
    """Generate both weekly reports."""
    
    print("=" * 60)
    print("🛒 CALGARY GROCERY HUB - WEEKLY REPORT GENERATOR v5.0")
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
    output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    page_url = _public_page_url()

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

    # === REPORT 3: FACEBOOK POST ===
    print(f"\n✍️ Generating FACEBOOK post...")
    facebook_post = generate_facebook_post(report_data, page_url=page_url or "(public page URL not configured)", use_ai=use_ai)
    facebook_filename = os.path.join(output_dir, f"weekly_post_FACEBOOK_{timestamp}.txt")
    with open(facebook_filename, 'w', encoding='utf-8') as f:
        f.write(facebook_post)
    print(f"   ✅ Saved: {facebook_filename}")

    # === LATEST BUNDLE (consumed by the public weekly web page) ===
    latest = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'week_ending': report_data['week_ending'],
        'total_deals': report_data['total_deals'],
        'page_url': page_url,
        'store_report': store_report,
        'category_report': category_report,
        'facebook_post': facebook_post,
    }
    latest_path = os.path.join(output_dir, LATEST_JSON)
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Saved: {latest_path}")

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
    
    return store_report, category_report, facebook_post


if __name__ == "__main__":
    import sys
    use_ai = "--no-ai" not in sys.argv
    
    generate_weekly_reports(use_ai=use_ai)
