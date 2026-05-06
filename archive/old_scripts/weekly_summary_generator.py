"""
═══════════════════════════════════════════════════════════════════════════════
Weekly Deals Summary Generator - Family Edition
═══════════════════════════════════════════════════════════════════════════════

PURPOSE: Create compelling weekly grocery summaries for families
AUDIENCE: Budget-conscious families doing meal planning
FOCUS: Needle-movers (proteins, dairy, produce, pantry staples)

Run this after get_deals.py to generate a weekly summary.
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
from datetime import datetime, timedelta
import os

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Files
CURRENT_FLYERS = 'current_flyers.csv'
HISTORICAL_ARCHIVE = 'historical_archive.csv'
OUTPUT_FILE = 'weekly_deals_summary.md'

# Priority categories (needle-movers for families)
PRIORITY_CATEGORIES = {
    'Proteins': ['Meat & Seafood'],
    'Dairy & Breakfast': ['Dairy & Eggs', 'Breakfast'],
    'Produce': ['Produce'],
    'Pantry Staples': ['Pantry', 'Bakery'],
    'Frozen Essentials': ['Frozen Foods']
}

# Deal criteria
GREAT_DEAL_SCORE = 85  # Score ≥85 is worth mentioning
SIGNIFICANT_SAVINGS = 0.20  # 20% below average
MIN_WEEKS_ABSENT = 6  # First time in 6+ weeks is notable

# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def load_data():
    """Load current and historical data."""
    df_current = pd.read_csv(CURRENT_FLYERS)
    df_archive = pd.read_csv(HISTORICAL_ARCHIVE) if os.path.exists(HISTORICAL_ARCHIVE) else pd.DataFrame()
    
    # Convert dates with mixed format handling
    df_current['Date'] = pd.to_datetime(df_current['Date'], format='mixed', errors='coerce')
    if len(df_archive) > 0:
        df_archive['Date'] = pd.to_datetime(df_archive['Date'], format='mixed', errors='coerce')
    
    return df_current, df_archive

def calculate_historical_avg(item_name, df_archive):
    """Calculate 12-week historical average for an item."""
    if len(df_archive) == 0:
        return None
    
    cutoff = pd.Timestamp.now() - timedelta(weeks=12)
    item_history = df_archive[
        (df_archive['Item'].str.lower() == item_name.lower()) &
        (df_archive['Date'] >= cutoff) &
        (df_archive['Price_Value'] > 0)
    ]
    
    if len(item_history) == 0:
        return None
    
    return item_history['Price_Value'].mean()

def weeks_since_last_seen(item_name, df_archive):
    """Calculate weeks since item was last on sale."""
    if len(df_archive) == 0:
        return None
    
    item_history = df_archive[
        (df_archive['Item'].str.lower() == item_name.lower()) &
        (df_archive['Price_Value'] > 0)
    ]
    
    if len(item_history) == 0:
        return None
    
    # Sort by date descending
    item_history = item_history.sort_values('Date', ascending=False)
    
    # Skip first entry (current week)
    if len(item_history) <= 1:
        return None
    
    last_seen = item_history.iloc[1]['Date']
    weeks_diff = (pd.Timestamp.now() - last_seen).days / 7
    
    return int(weeks_diff)

def categorize_items(df_current):
    """Group items by priority categories."""
    categorized = {}
    
    for priority_cat, ai_categories in PRIORITY_CATEGORIES.items():
        items = df_current[df_current['ai_category'].isin(ai_categories)]
        categorized[priority_cat] = items
    
    return categorized

def get_top_deals_by_category(items, df_archive, limit=5):
    """Get top deals in a category with context."""
    
    deals = []
    
    for _, item in items.iterrows():
        # Skip low scores
        if item['ai_deal_score'] < GREAT_DEAL_SCORE:
            continue
        
        deal_info = {
            'item_name': item['Item'],
            'price': item['Price_Value'],
            'price_text': item['Price_Text'],
            'store': item['Store'],
            'score': item['ai_deal_score'],
            'explanation': item['ai_explanation'],
            'is_member': item.get('is_member_exclusive', False),
            'is_featured': item.get('is_featured', False)
        }
        
        # Calculate savings vs historical average
        hist_avg = calculate_historical_avg(item['Item'], df_archive)
        if hist_avg and hist_avg > 0:
            savings_pct = (hist_avg - item['Price_Value']) / hist_avg
            deal_info['hist_avg'] = hist_avg
            deal_info['savings_pct'] = savings_pct
        else:
            deal_info['hist_avg'] = None
            deal_info['savings_pct'] = None
        
        # Check if first time in a while
        weeks_absent = weeks_since_last_seen(item['Item'], df_archive)
        if weeks_absent and weeks_absent >= MIN_WEEKS_ABSENT:
            deal_info['weeks_absent'] = weeks_absent
            deal_info['notable'] = True
        else:
            deal_info['weeks_absent'] = None
            deal_info['notable'] = False
        
        deals.append(deal_info)
    
    # Sort by score, then by savings percentage
    deals.sort(key=lambda x: (x['score'], x['savings_pct'] or 0), reverse=True)
    
    return deals[:limit]

def format_price(price):
    """Format price nicely."""
    if price < 1:
        return f"{price*100:.0f}¢"
    return f"${price:.2f}"

def format_deal_item(deal):
    """Format a single deal item for display."""
    
    # Base info
    parts = [f"**{deal['item_name']} - {deal['price_text']}** ({deal['store']})"]
    
    # Add context
    context = []
    
    if deal['savings_pct'] and deal['savings_pct'] >= SIGNIFICANT_SAVINGS:
        context.append(f"{deal['savings_pct']*100:.0f}% below 12-week avg")
    
    if deal['score'] >= 90:
        context.append("BEST PRICE")
    
    if deal['weeks_absent'] and deal['weeks_absent'] >= MIN_WEEKS_ABSENT:
        context.append(f"First time in {deal['weeks_absent']} weeks")
    
    if deal['is_member']:
        context.append("Member Exclusive")
    
    if deal['is_featured']:
        context.append("Featured Deal")
    
    if context:
        parts.append("   → " + " | ".join(context))
    
    # Add explanation if meaningful
    if deal['explanation'] and "unavailable" not in deal['explanation'].lower():
        # Shorten explanation if too long
        explanation = deal['explanation']
        if len(explanation) > 120:
            explanation = explanation[:117] + "..."
        parts.append(f"   💡 {explanation}")
    
    return "\n".join(parts)

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_weekly_overview(df_current, df_archive):
    """Generate opening narrative about the week overall."""
    
    # Get key stats
    total_items = len(df_current)
    stores = df_current['Store'].nunique()
    great_deals = len(df_current[df_current['ai_deal_score'] >= GREAT_DEAL_SCORE])
    exceptional_deals = len(df_current[df_current['ai_deal_score'] >= 90])
    member_exclusives = df_current.get('is_member_exclusive', pd.Series([False])).sum()
    
    # Get date range
    valid_until = pd.to_datetime(df_current['Valid_Until'].iloc[0]) if 'Valid_Until' in df_current.columns else None
    week_start = datetime.now()
    week_end = valid_until if valid_until else week_start + timedelta(days=7)
    
    # Determine best category this week
    categorized = categorize_items(df_current)
    best_category = None
    best_category_count = 0
    
    for cat_name, items in categorized.items():
        great_deals_in_cat = len(items[items['ai_deal_score'] >= GREAT_DEAL_SCORE])
        if great_deals_in_cat > best_category_count:
            best_category_count = great_deals_in_cat
            best_category = cat_name
    
    # Generate narrative
    narrative = f"""# 🛒 Calgary Grocery Deals - Week of {week_start.strftime('%b %d')}-{week_end.strftime('%d, %Y')}

## 📊 This Week's Shopping Landscape

This week brings **{great_deals} notable deals** across {stores} Calgary stores, with {exceptional_deals} truly exceptional opportunities worth planning your meals around."""
    
    if best_category and best_category_count > 0:
        narrative += f" **{best_category}** stands out this week with {best_category_count} standout deals - great timing for families stocking up on essentials."
    
    if member_exclusives > 0:
        narrative += f"\n\n💳 **Member Tip:** {member_exclusives} deals this week require store memberships (Co-op, Save-On More Rewards, PC Optimum, etc.). If you're not a member, these programs often pay for themselves in a single shopping trip."
    
    narrative += "\n\n**Smart Shopping Strategy:** Focus on the proteins and produce highlighted below, then build your meals around what's actually on sale. Buying featured proteins at 20-30% off and freezing them can save your family hundreds per month.\n"
    
    return narrative

def generate_summary():
    """Generate complete weekly summary."""
    
    print("=" * 80)
    print("GENERATING WEEKLY DEALS SUMMARY")
    print("=" * 80)
    
    # Load data
    print("\n📂 Loading data...")
    df_current, df_archive = load_data()
    print(f"   Current items: {len(df_current)}")
    print(f"   Historical items: {len(df_archive)}")
    
    # Generate overview
    print("\n📝 Generating overview...")
    summary = generate_weekly_overview(df_current, df_archive)
    
    # Process each priority category
    print("\n🏷️  Processing categories...")
    categorized = categorize_items(df_current)
    
    for cat_name, items in categorized.items():
        if len(items) == 0:
            continue
        
        print(f"   {cat_name}: {len(items)} items")
        
        top_deals = get_top_deals_by_category(items, df_archive, limit=5)
        
        if len(top_deals) == 0:
            continue
        
        summary += f"\n---\n\n## 🎯 {cat_name}\n\n"
        
        # Add best of week if score ≥90
        best_deal = top_deals[0]
        if best_deal['score'] >= 90:
            summary += f"**BEST OF WEEK:**\n🏆 "
            summary += format_deal_item(best_deal)
            summary += "\n\n"
            top_deals = top_deals[1:]  # Remove from list
        
        if len(top_deals) > 0:
            summary += "**Also Worth It:**\n"
            for deal in top_deals:
                summary += "• " + format_deal_item(deal).replace('\n', '\n  ') + "\n\n"
    
    # Add meal planning section
    print("\n💡 Adding meal planning tips...")
    summary += generate_meal_planning_section(df_current, df_archive)
    
    # Add budget impact
    print("\n💰 Calculating budget impact...")
    summary += generate_budget_impact(df_current, df_archive)
    
    # Save
    print(f"\n💾 Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    print(f"\n✅ Summary generated successfully!")
    print(f"   File: {OUTPUT_FILE}")
    print(f"   Size: {len(summary)} characters")
    
    return summary

def generate_meal_planning_section(df_current, df_archive):
    """Generate meal planning tips based on deals."""
    
    # Find top protein deals
    proteins = df_current[df_current['ai_category'] == 'Meat & Seafood']
    top_proteins = get_top_deals_by_category(proteins, df_archive, limit=3)
    
    # Find complementary items
    produce = df_current[df_current['ai_category'] == 'Produce']
    top_produce = get_top_deals_by_category(produce, df_archive, limit=2)
    
    if len(top_proteins) == 0:
        return ""
    
    section = "\n---\n\n## 💡 Meal Planning Strategy\n\n"
    
    protein_names = [p['item_name'] for p in top_proteins]
    protein_text = ", ".join(protein_names[:2])
    if len(protein_names) > 2:
        protein_text += f", and {protein_names[2]}"
    
    section += f"With **{protein_text}** at great prices this week, it's an ideal time to meal prep protein-forward dinners. "
    
    if len(top_produce) > 0:
        produce_names = [p['item_name'] for p in top_produce]
        section += f"Pair with featured **{produce_names[0]}** for complete, budget-friendly meals.\n\n"
    else:
        section += "\n\n"
    
    section += "**This Week's Meal Ideas:**\n"
    
    # Generate meal ideas based on proteins
    for protein in top_proteins[:3]:
        name = protein['item_name'].lower()
        if 'chicken' in name:
            section += "• Chicken stir-fry, grilled chicken Caesar, or chicken fajitas\n"
        elif 'beef' in name or 'ground' in name:
            section += "• Spaghetti with meat sauce, tacos, or shepherd's pie\n"
        elif 'pork' in name:
            section += "• Pork chops with roasted vegetables, pulled pork, or stir-fry\n"
        elif 'salmon' in name or 'fish' in name:
            section += "• Baked salmon with veggies, fish tacos, or salmon bowls\n"
    
    return section

def generate_budget_impact(df_current, df_archive):
    """Calculate potential savings for families."""
    
    # Get top 5 deals overall
    top_deals = df_current[df_current['ai_deal_score'] >= GREAT_DEAL_SCORE].nlargest(5, 'ai_deal_score')
    
    if len(top_deals) == 0:
        return ""
    
    section = "\n---\n\n## 💰 Budget Impact\n\n"
    
    total_savings = 0
    items_analyzed = 0
    
    for _, item in top_deals.iterrows():
        hist_avg = calculate_historical_avg(item['Item'], df_archive)
        if hist_avg and hist_avg > item['Price_Value']:
            savings = hist_avg - item['Price_Value']
            total_savings += savings
            items_analyzed += 1
    
    if items_analyzed > 0:
        avg_savings = total_savings / items_analyzed
        
        section += f"**Typical Family Savings:** By taking advantage of just the top {items_analyzed} deals this week, "
        section += f"a family can save approximately **${total_savings:.2f}** compared to recent average prices.\n\n"
        
        section += f"**Annual Impact:** If you consistently shop the weekly deals, these savings add up to "
        section += f"**${total_savings * 52:.0f}+** per year - enough for a family vacation!\n"
    else:
        section += "Shop the deals above to maximize your grocery budget this week.\n"
    
    return section

# ═══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    summary = generate_summary()
    
    print("\n" + "=" * 80)
    print("PREVIEW:")
    print("=" * 80)
    print(summary[:500] + "...\n")
    print(f"\n💡 Open {OUTPUT_FILE} to see the full summary!")
