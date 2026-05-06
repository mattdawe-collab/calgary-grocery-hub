"""
═══════════════════════════════════════════════════════════════════════════════
AI Quality Analyzer - ENHANCED with Full Context
═══════════════════════════════════════════════════════════════════════════════

VERSION: 2.0 - Maximum Context Architecture
AUTHOR: Built with Claude (Anthropic)

WHAT'S NEW IN V2.0:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Rich Historical Context
   - Price ranges (min/max/avg over 12 weeks)
   - Price trends (increasing/decreasing/stable)
   - Best price ever seen
   - Frequency analysis (how often on sale)

✅ PDF Calibration Signals
   - Member exclusive detection
   - Featured item prominence
   - Price validation status

✅ Smart Categories
   - 20-category hierarchy
   - Subcategory assignment
   - Stats Canada benchmark integration

✅ Intelligent Deal Scoring
   - Multi-factor scoring (price, trend, quality, frequency)
   - Context-aware recommendations
   - Personalized explanations

CLAUDE RECEIVES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example prompt for "Maple Leaf Bacon $5.99":

Historical Context:
- This item's price range over last 12 weeks: $5.99 - $8.99 (avg: $7.49)
- Current price $5.99 is at MINIMUM (best price seen!)
- Price trend: DECREASING (was $8.99 last week)
- Seen 8 times in last 12 weeks (frequent sale item)

PDF Calibration:
- Member Exclusive: YES (requires membership)
- Featured Item: YES (page 1, red circle, high prominence)
- Price Validated: YES (cross-checked against PDF)

This gives Claude EVERYTHING it needs for intelligent analysis!
═══════════════════════════════════════════════════════════════════════════════
"""

import anthropic
import os
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Category hierarchy (20 core categories)
CATEGORIES = {
    "Produce": ["Fresh Vegetables", "Fresh Fruit", "Salads & Herbs", "Organic Produce"],
    "Meat & Seafood": ["Beef", "Pork", "Chicken", "Seafood", "Deli Meats"],
    "Dairy & Eggs": ["Milk & Cream", "Cheese", "Yogurt", "Eggs", "Butter"],
    "Bakery": ["Bread", "Bagels & Buns", "Pastries", "Cakes"],
    "Frozen Foods": ["Frozen Meals", "Ice Cream", "Frozen Vegetables", "Frozen Pizza"],
    "Pantry": ["Pasta & Rice", "Canned Goods", "Sauces & Condiments", "Baking Supplies"],
    "Snacks": ["Chips & Crackers", "Candy", "Nuts & Seeds", "Granola Bars"],
    "Beverages": ["Soft Drinks", "Juice", "Coffee & Tea", "Water"],
    "Breakfast": ["Cereal", "Oatmeal", "Breakfast Bars", "Syrup"],
    "Health & Wellness": ["Vitamins", "Supplements", "Protein Powder", "Health Foods"],
    "Baby & Kids": ["Baby Food", "Diapers", "Formula", "Kids Snacks"],
    "Household": ["Cleaning Supplies", "Paper Products", "Laundry", "Trash Bags"],
    "Personal Care": ["Bath & Body", "Hair Care", "Oral Care", "Cosmetics"],
    "Pet Supplies": ["Pet Food", "Pet Treats", "Pet Care"],
    "Alcohol": ["Beer", "Wine", "Spirits"],
    "International": ["Asian Foods", "Mexican Foods", "European Foods"],
    "Organic & Natural": ["Organic Groceries", "Natural Products", "Gluten-Free"],
    "Deli & Prepared": ["Prepared Meals", "Rotisserie Chicken", "Sandwiches"],
    "Seasonal": ["Holiday Items", "Seasonal Produce", "Seasonal Decor"],
    "General": ["Miscellaneous", "Other"]
}

# ═══════════════════════════════════════════════════════════════════════════
# HISTORICAL ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def calculate_historical_stats(item_name, store, df_archive):
    """
    Calculate comprehensive historical statistics for an item.
    
    Returns:
    - min_price: Lowest price seen
    - max_price: Highest price seen
    - avg_price: Average price
    - median_price: Median price
    - price_trend: "INCREASING", "DECREASING", "STABLE"
    - frequency: How many times seen
    - weeks_tracked: How many weeks of data
    - last_seen_price: Most recent price
    - last_seen_date: When last seen
    """
    
    if df_archive is None or len(df_archive) == 0:
        return None
    
    # Filter for this specific item at this store
    item_history = df_archive[
        (df_archive['Item'].str.lower() == item_name.lower()) & 
        (df_archive['Store'] == store)
    ].copy()
    
    if len(item_history) == 0:
        # Try just item name (any store)
        item_history = df_archive[
            df_archive['Item'].str.lower() == item_name.lower()
        ].copy()
    
    if len(item_history) == 0:
        return None
    
    # Get last 12 weeks only
    cutoff_date = pd.Timestamp.now() - timedelta(weeks=12)
    if 'Date' in item_history.columns:
        item_history['Date'] = pd.to_datetime(item_history['Date'], errors='coerce')
        item_history = item_history[item_history['Date'] >= cutoff_date]
    
    if len(item_history) == 0:
        return None
    
    # Calculate statistics
    prices = item_history['Price_Value'].dropna()
    prices = prices[prices > 0]  # Exclude zero prices
    
    if len(prices) == 0:
        return None
    
    stats = {
        'min_price': float(prices.min()),
        'max_price': float(prices.max()),
        'avg_price': float(prices.mean()),
        'median_price': float(prices.median()),
        'frequency': len(item_history),
        'weeks_tracked': len(item_history['Date'].dt.isocalendar().week.unique()) if 'Date' in item_history.columns else len(item_history)
    }
    
    # Price trend analysis
    if 'Date' in item_history.columns and len(item_history) >= 2:
        recent = item_history.nlargest(3, 'Date')
        older = item_history.nsmallest(3, 'Date')
        
        recent_avg = recent['Price_Value'].mean()
        older_avg = older['Price_Value'].mean()
        
        if recent_avg < older_avg * 0.95:
            stats['price_trend'] = "DECREASING"
        elif recent_avg > older_avg * 1.05:
            stats['price_trend'] = "INCREASING"
        else:
            stats['price_trend'] = "STABLE"
        
        # Last seen info
        latest = item_history.nlargest(1, 'Date').iloc[0]
        stats['last_seen_price'] = float(latest['Price_Value'])
        stats['last_seen_date'] = latest['Date'].strftime('%Y-%m-%d')
    else:
        stats['price_trend'] = "UNKNOWN"
        stats['last_seen_price'] = float(prices.iloc[-1])
        stats['last_seen_date'] = "Unknown"
    
    return stats

def format_historical_context(item_name, current_price, stats):
    """Format historical stats into human-readable context."""
    
    if not stats:
        return "No historical data available (new item)."
    
    context_parts = []
    
    # Price range
    context_parts.append(f"Historical price range: ${stats['min_price']:.2f} - ${stats['max_price']:.2f} (avg: ${stats['avg_price']:.2f})")
    
    # Current price vs history
    if current_price <= stats['min_price'] * 1.02:
        context_parts.append(f"Current ${current_price:.2f} is at/near MINIMUM (best price seen!)")
    elif current_price >= stats['max_price'] * 0.98:
        context_parts.append(f"Current ${current_price:.2f} is at/near MAXIMUM (highest price)")
    elif current_price <= stats['avg_price'] * 0.9:
        context_parts.append(f"Current ${current_price:.2f} is BELOW average (good deal)")
    elif current_price >= stats['avg_price'] * 1.1:
        context_parts.append(f"Current ${current_price:.2f} is ABOVE average (expensive)")
    else:
        context_parts.append(f"Current ${current_price:.2f} is near average")
    
    # Trend
    if stats['price_trend'] == "DECREASING":
        context_parts.append(f"Price trend: DECREASING (getting cheaper)")
    elif stats['price_trend'] == "INCREASING":
        context_parts.append(f"Price trend: INCREASING (getting more expensive)")
    else:
        context_parts.append(f"Price trend: STABLE")
    
    # Frequency
    context_parts.append(f"Seen {stats['frequency']} times over {stats['weeks_tracked']} weeks")
    
    return " | ".join(context_parts)

def format_pdf_context(row):
    """Format PDF calibration signals into context."""
    
    context_parts = []
    
    if row.get('is_member_exclusive') == True:
        context_parts.append("⭐ MEMBER EXCLUSIVE (requires membership)")
    
    if row.get('is_featured') == True:
        page = row.get('pdf_page', 'unknown')
        context_parts.append(f"🎯 FEATURED ITEM (page {page}, high visual prominence)")
    
    if row.get('price_validated') == True:
        context_parts.append("✅ Price validated against PDF")
    
    if not context_parts:
        return None
    
    return " | ".join(context_parts)

# ═══════════════════════════════════════════════════════════════════════════
# AI ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_batch_with_ai(batch_items, df_archive):
    """
    Analyze a batch of items with Claude, providing rich context.
    
    Args:
        batch_items: List of dict with keys: Item, Price_Value, Store, (optional PDF calibration)
        df_archive: Historical dataframe for context
    
    Returns:
        List of dict with AI analysis results
    """
    
    if not ANTHROPIC_API_KEY:
        print("   ⚠️  ANTHROPIC_API_KEY not found - skipping AI analysis")
        return [create_fallback_analysis(item) for item in batch_items]
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Build rich prompt with historical and PDF context
    items_text = []
    for idx, item in enumerate(batch_items, 1):
        item_name = item['Item']
        price = item['Price_Value']
        store = item['Store']
        
        # Get historical statistics
        hist_stats = calculate_historical_stats(item_name, store, df_archive)
        hist_context = format_historical_context(item_name, price, hist_stats)
        
        # Get PDF calibration context
        pdf_context = format_pdf_context(item)
        
        # Build item description
        item_desc = f"""
{idx}. {item_name} - ${price:.2f} at {store}
   Historical: {hist_context}"""
        
        if pdf_context:
            item_desc += f"\n   Calibration: {pdf_context}"
        
        items_text.append(item_desc)
    
    items_block = "\n".join(items_text)
    
    prompt = f"""You are analyzing grocery deals for Calgary shoppers. For each item below, provide:

1. **Category** (choose ONE from this list):
   Produce, Meat & Seafood, Dairy & Eggs, Bakery, Frozen Foods, Pantry, Snacks, 
   Beverages, Breakfast, Health & Wellness, Baby & Kids, Household, Personal Care, 
   Pet Supplies, Alcohol, International, Organic & Natural, Deli & Prepared, 
   Seasonal, General

2. **Subcategory** (specific type within category)

3. **Deal Score** (0-100):
   - 90-100: Exceptional deal (lowest price seen, member exclusive, featured)
   - 75-89: Great deal (below average, good trend)
   - 60-74: Good deal (decent price)
   - 40-59: Fair deal (average price)
   - 0-39: Poor deal (above average or expensive)

4. **Explanation** (1-2 sentences):
   - Reference historical context when available
   - Mention if it's a member exclusive or featured item
   - Explain why the score makes sense
   - Be specific about savings or value

ITEMS TO ANALYZE:
{items_block}

OUTPUT FORMAT (JSON array):
[
  {{
    "item_number": 1,
    "category": "category name",
    "subcategory": "subcategory name",
    "deal_score": 85,
    "explanation": "Explanation here"
  }},
  ...
]

Respond with ONLY the JSON array, no other text."""

    try:
        # Add timeout protection (30 second timeout)
        api_start = time.time()
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=1.0,
            messages=[
                {"role": "user", "content": prompt}
            ],
            timeout=30.0  # 30 second timeout
        )
        
        api_elapsed = time.time() - api_start
        print(f"         API response received in {api_elapsed:.1f}s")
        
        # Parse response
        response_text = response.content[0].text.strip()
        
        # Extract JSON (handle markdown fences)
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        import json
        results = json.loads(response_text)
        
        print(f"         JSON parsed successfully ({len(results)} items)")
        
        # Map results back to items
        analysis_results = []
        for item, result in zip(batch_items, results):
            analysis_results.append({
                'Item': item['Item'],
                'ai_category': result.get('category', 'General'),
                'ai_sub_category': result.get('subcategory', result.get('category', 'General')),
                'ai_deal_score': result.get('deal_score', 50),
                'ai_explanation': result.get('explanation', 'No analysis available')
            })
        
        return analysis_results
        
    except TimeoutError:
        print(f"   ⚠️  API timeout after 30 seconds - retrying with smaller batch...")
        # Retry with half the batch size
        if len(batch_items) > 10:
            mid = len(batch_items) // 2
            first_half = analyze_batch_with_ai(batch_items[:mid], df_archive)
            time.sleep(2)
            second_half = analyze_batch_with_ai(batch_items[mid:], df_archive)
            return first_half + second_half
        else:
            print(f"   ⚠️  Batch too small to split - using fallback")
            return [create_fallback_analysis(item) for item in batch_items]
            
    except json.JSONDecodeError as e:
        print(f"   ⚠️  JSON parse error: {str(e)[:80]}")
        print(f"   Response preview: {response_text[:200]}...")
        return [create_fallback_analysis(item) for item in batch_items]
        
    except Exception as e:
        print(f"   ⚠️  AI analysis error: {str(e)[:100]}")
        return [create_fallback_analysis(item) for item in batch_items]

def create_fallback_analysis(item):
    """Create basic analysis when AI fails."""
    return {
        'Item': item['Item'],
        'ai_category': 'General',
        'ai_sub_category': 'General',
        'ai_deal_score': 50,
        'ai_explanation': 'AI analysis unavailable - check manually'
    }

# ═══════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def add_ai_analysis_to_dataframe(df_new, df_archive=None, batch_size=50):
    """
    Add AI analysis to new items with full historical and PDF context.
    
    Args:
        df_new: DataFrame of new items to analyze
        df_archive: Historical DataFrame for context (optional but recommended)
        batch_size: Number of items to analyze per API call
    
    Returns:
        DataFrame with added columns:
        - ai_category
        - ai_sub_category
        - ai_deal_score
        - ai_explanation
    """
    
    if len(df_new) == 0:
        return df_new
    
    print(f"\n🤖 AI ANALYSIS - Enhanced with Full Context")
    print(f"   Items to analyze: {len(df_new)}")
    
    if df_archive is not None and len(df_archive) > 0:
        print(f"   Historical records: {len(df_archive):,}")
        print(f"   ✅ Claude will receive historical price context")
    else:
        print(f"   ⚠️  No historical data - limited context")
    
    # Check for PDF calibration columns
    pdf_columns = ['is_member_exclusive', 'is_featured', 'price_validated']
    has_pdf_data = any(col in df_new.columns for col in pdf_columns)
    
    if has_pdf_data:
        member_count = df_new.get('is_member_exclusive', pd.Series([False])).sum()
        featured_count = df_new.get('is_featured', pd.Series([False])).sum()
        print(f"   ✅ Claude will receive PDF calibration signals")
        print(f"      Member exclusives: {member_count}")
        print(f"      Featured items: {featured_count}")
    
    # Process in batches with detailed progress tracking
    import time
    all_results = []
    total_batches = (len(df_new) + batch_size - 1) // batch_size
    
    start_time = time.time()
    batch_times = []
    
    for batch_num in range(total_batches):
        batch_start = time.time()
        
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(df_new))
        
        batch_df = df_new.iloc[start_idx:end_idx]
        
        # Calculate progress and ETA
        progress_pct = (batch_num / total_batches) * 100
        items_done = batch_num * batch_size
        items_remaining = len(df_new) - items_done
        
        # Estimate time remaining
        if batch_times:
            avg_batch_time = sum(batch_times) / len(batch_times)
            batches_remaining = total_batches - batch_num
            eta_seconds = avg_batch_time * batches_remaining
            eta_minutes = int(eta_seconds / 60)
            eta_seconds_remainder = int(eta_seconds % 60)
            eta_str = f"{eta_minutes}m {eta_seconds_remainder}s" if eta_minutes > 0 else f"{eta_seconds_remainder}s"
        else:
            eta_str = "calculating..."
        
        # Current timestamp
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n   📦 [{current_time}] Batch {batch_num + 1}/{total_batches} ({progress_pct:.1f}% complete)")
        print(f"      Items: {items_done}/{len(df_new)} done, {items_remaining} remaining")
        print(f"      ETA: {eta_str}")
        print(f"      Processing: {len(batch_df)} items...")
        
        # Convert to list of dicts for API
        batch_items = []
        for _, row in batch_df.iterrows():
            item_dict = {
                'Item': row['Item'],
                'Price_Value': row['Price_Value'],
                'Store': row['Store']
            }
            # Add PDF calibration if available
            for col in pdf_columns:
                if col in row:
                    item_dict[col] = row[col]
            
            batch_items.append(item_dict)
        
        # Show we're calling API (this is where it might stall)
        print(f"      🔄 Calling Claude API...")
        
        # Analyze batch
        batch_results = analyze_batch_with_ai(batch_items, df_archive)
        all_results.extend(batch_results)
        
        # Calculate batch time
        batch_elapsed = time.time() - batch_start
        batch_times.append(batch_elapsed)
        
        print(f"      ✅ Complete in {batch_elapsed:.1f}s")
        
        # Show average time per batch
        if len(batch_times) >= 3:
            avg_time = sum(batch_times[-3:]) / 3  # Use last 3 batches
            print(f"      📊 Avg batch time: {avg_time:.1f}s")
    
    # Create results dataframe
    results_df = pd.DataFrame(all_results)
    
    # Merge back to original
    df_new = df_new.merge(
        results_df,
        on='Item',
        how='left'
    )
    
    # Fill missing AI columns
    df_new['ai_category'] = df_new['ai_category'].fillna('General')
    df_new['ai_sub_category'] = df_new['ai_sub_category'].fillna('General')
    df_new['ai_deal_score'] = df_new['ai_deal_score'].fillna(50)
    df_new['ai_explanation'] = df_new['ai_explanation'].fillna('No analysis available')
    
    # Calculate total time
    total_elapsed = time.time() - start_time
    total_minutes = int(total_elapsed / 60)
    total_seconds = int(total_elapsed % 60)
    
    # Statistics
    print(f"\n" + "=" * 80)
    print(f"📊 AI ANALYSIS COMPLETE")
    print(f"=" * 80)
    print(f"   Total time: {total_minutes}m {total_seconds}s" if total_minutes > 0 else f"   Total time: {total_seconds}s")
    print(f"   Items analyzed: {len(df_new)}")
    print(f"   Batches processed: {total_batches}")
    if batch_times:
        print(f"   Avg time per batch: {sum(batch_times)/len(batch_times):.1f}s")
    print(f"\n   Avg deal score: {df_new['ai_deal_score'].mean():.1f}/100")
    print(f"   Exceptional deals (90+): {(df_new['ai_deal_score'] >= 90).sum()}")
    print(f"   Great deals (75-89): {((df_new['ai_deal_score'] >= 75) & (df_new['ai_deal_score'] < 90)).sum()}")
    print(f"   Good deals (60-74): {((df_new['ai_deal_score'] >= 60) & (df_new['ai_deal_score'] < 75)).sum()}")
    print(f"=" * 80)
    
    return df_new

# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 80)
    print("AI Quality Analyzer v2.0 - Test Mode")
    print("=" * 80)
    
    # Test with sample data
    test_items = pd.DataFrame([
        {
            'Item': 'Maple Leaf Natural Bacon',
            'Price_Value': 5.99,
            'Store': 'Sobeys',
            'is_member_exclusive': True,
            'is_featured': True,
            'pdf_page': 1
        },
        {
            'Item': 'Blueberries',
            'Price_Value': 3.97,
            'Store': 'Calgary Co-op',
            'is_member_exclusive': False,
            'is_featured': False
        }
    ])
    
    # Test historical data
    test_history = pd.DataFrame([
        {
            'Item': 'Maple Leaf Natural Bacon',
            'Price_Value': 8.99,
            'Store': 'Sobeys',
            'Date': pd.Timestamp('2024-12-01')
        },
        {
            'Item': 'Maple Leaf Natural Bacon',
            'Price_Value': 7.99,
            'Store': 'Sobeys',
            'Date': pd.Timestamp('2024-12-15')
        }
    ])
    
    print("\nTest items:")
    print(test_items)
    
    print("\nTest history:")
    print(test_history)
    
    # Run analysis
    result = add_ai_analysis_to_dataframe(test_items, test_history, batch_size=10)
    
    print("\n" + "=" * 80)
    print("RESULTS:")
    print("=" * 80)
    print(result[['Item', 'Price_Value', 'ai_category', 'ai_deal_score', 'ai_explanation']])
