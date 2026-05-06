"""
Data Diagnostic Script
Run this to see what's actually in your grocery data
"""

import pandas as pd

print("=" * 80)
print("CALGARY GROCERY HUB - DATA DIAGNOSTIC")
print("=" * 80)

# Load the data
try:
    df = pd.read_csv('clean_grocery_data.csv')
    print(f"\n✅ Loaded clean_grocery_data.csv: {len(df)} records")
    
    # Convert date columns to datetime
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['valid_until'] = pd.to_datetime(df['valid_until'], errors='coerce')
    
except Exception as e:
    print(f"\n❌ Could not load clean_grocery_data.csv: {e}")
    exit()

# Check columns
print("\n" + "=" * 80)
print("COLUMNS PRESENT:")
print("=" * 80)
for col in df.columns:
    print(f"  - {col}")

# Check for the specific items from your screenshot
print("\n" + "=" * 80)
print("ANALYZING ITEMS FROM SCREENSHOT:")
print("=" * 80)

test_items = [
    "Sweet Potatoes",
    "Butterball Turkey",
    "Coca-Cola Or Pepsi Soft Drinks",
    "Kettle Chips"
]

for item_name in test_items:
    print(f"\n🔍 {item_name}:")
    matches = df[df['item'].str.contains(item_name, case=False, na=False)]
    
    if matches.empty:
        print("   ❌ Not found in data")
        continue
    
    print(f"   Found {len(matches)} records")
    
    # Show current price
    current = matches.nlargest(1, 'date')
    if not current.empty:
        row = current.iloc[0]
        print(f"   Current Price: ${row.get('price', 'N/A')}")
        print(f"   Store: {row.get('store', 'N/A')}")
        print(f"   Date: {row.get('date', 'N/A')}")
        print(f"   Original Price: ${row.get('original_price', 'N/A')}")
        print(f"   Savings %: {row.get('savings_pct', 'N/A')}")
        if 'normalized_price' in df.columns:
            print(f"   Normalized: {row.get('normalized_price', 'N/A')}")
    
    # Show historical prices
    print(f"   Historical prices:")
    price_stats = matches['price'].describe()
    print(f"      Min: ${price_stats['min']:.2f}")
    print(f"      Avg: ${price_stats['mean']:.2f}")
    print(f"      Max: ${price_stats['max']:.2f}")
    print(f"      Count: {int(price_stats['count'])}")
    
    # Show recent history
    print(f"   Last 3 appearances:")
    recent = matches.nlargest(3, 'date')[['date', 'store', 'price']]
    for _, r in recent.iterrows():
        print(f"      {r['date']} @ {r['store']}: ${r['price']:.2f}")

# Check deal scores
print("\n" + "=" * 80)
print("DEAL SCORE DISTRIBUTION:")
print("=" * 80)

if 'deal_score' in df.columns:
    print(f"  Min: {df['deal_score'].min():.1f}")
    print(f"  Avg: {df['deal_score'].mean():.1f}")
    print(f"  Max: {df['deal_score'].max():.1f}")
    print(f"\n  Score Ranges:")
    print(f"    0-20:    {len(df[df['deal_score'] <= 20])} items")
    print(f"    21-40:   {len(df[(df['deal_score'] > 20) & (df['deal_score'] <= 40)])} items")
    print(f"    41-60:   {len(df[(df['deal_score'] > 40) & (df['deal_score'] <= 60)])} items")
    print(f"    61-80:   {len(df[(df['deal_score'] > 60) & (df['deal_score'] <= 80)])} items")
    print(f"    81-100:  {len(df[df['deal_score'] > 80])} items (EXCELLENT)")
else:
    print("  ❌ deal_score column not found (this is calculated by dashboard)")

# Check savings
print("\n" + "=" * 80)
print("SAVINGS ANALYSIS:")
print("=" * 80)

if 'savings_pct' in df.columns:
    has_savings = df[df['savings_pct'] > 0]
    print(f"  Items with advertised savings: {len(has_savings)} / {len(df)}")
    print(f"  Avg savings (when present): {has_savings['savings_pct'].mean():.1f}%")
    
    if len(has_savings) > 0:
        print(f"\n  Top 5 savings:")
        top_savings = df.nlargest(5, 'savings_pct')[['item', 'store', 'price', 'original_price', 'savings_pct']]
        for _, r in top_savings.iterrows():
            print(f"    {r['item']}: ${r['price']:.2f} (was ${r['original_price']:.2f}) = {r['savings_pct']:.0f}% off")
    else:
        print("\n  ⚠️  NO ITEMS have advertised savings!")
        print("     This is why all savings show 0% in the dashboard")
        print("     Flyers don't provide 'original price' data")
else:
    print("  ❌ savings_pct column not found")

# Check dates
print("\n" + "=" * 80)
print("DATE ANALYSIS:")
print("=" * 80)

if 'valid_until' in df.columns:
    date_counts = df.groupby('valid_until').size().sort_index()
    print(f"  Unique expiry dates:")
    for date, count in date_counts.items():
        print(f"    {date.strftime('%Y-%m-%d')}: {count} items")

print("\n" + "=" * 80)
print("DIAGNOSTIC COMPLETE")
print("=" * 80)
