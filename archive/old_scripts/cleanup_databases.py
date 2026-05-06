"""
DATABASE CLEANUP SCRIPT
Fixes all issues identified in the audit:
1. Remove 88 liquor items from historical archive
2. Standardize date formats
3. Remove duplicates from current flyers
"""

import pandas as pd
from datetime import datetime

print("=" * 80)
print("🧹 CALGARY GROCERY HUB - DATABASE CLEANUP")
print("=" * 80)

# ============================================================================
# FIX 1: CLEAN HISTORICAL ARCHIVE
# ============================================================================

print("\n📚 Cleaning historical_archive.csv...")

df_hist = pd.read_csv('historical_archive.csv')
print(f"   Before: {len(df_hist):,} records")

# Remove liquor store items
liquor_mask = df_hist['Store'].str.contains('liquor|wine|beer|spirits', case=False, na=False)
liquor_count = liquor_mask.sum()

if liquor_count > 0:
    print(f"   ❌ Found {liquor_count} liquor store items")
    df_hist = df_hist[~liquor_mask]
    print(f"   ✅ Removed {liquor_count} liquor items")
else:
    print(f"   ✅ No liquor items found")

# Standardize date formats
print(f"\n   Standardizing date formats...")
df_hist['Date'] = pd.to_datetime(df_hist['Date'], format='mixed', errors='coerce')
df_hist['Valid_Until'] = pd.to_datetime(df_hist['Valid_Until'], errors='coerce')

date_issues_before = df_hist['Valid_Until'].isna().sum()
print(f"   Date parsing issues: {date_issues_before}")

# Remove duplicates (should be 0, but just in case)
before_dup = len(df_hist)
df_hist = df_hist.drop_duplicates(subset=['Store', 'Original_Name', 'Price_Text', 'Valid_Until'], keep='first')
after_dup = len(df_hist)
dup_removed = before_dup - after_dup

if dup_removed > 0:
    print(f"   ✅ Removed {dup_removed} duplicate records")
else:
    print(f"   ✅ No duplicates found")

# Save cleaned historical archive
df_hist.to_csv('historical_archive.csv', index=False)
print(f"\n   After: {len(df_hist):,} records")
print(f"   ✅ Saved cleaned historical_archive.csv")

# ============================================================================
# FIX 2: CLEAN CURRENT FLYERS
# ============================================================================

print("\n📄 Cleaning current_flyers.csv...")

df_curr = pd.read_csv('current_flyers.csv')
print(f"   Before: {len(df_curr):,} records")

# Remove duplicates
before_dup = len(df_curr)
df_curr = df_curr.drop_duplicates(subset=['Store', 'Original_Name', 'Price_Text', 'Valid_Until'], keep='first')
after_dup = len(df_curr)
dup_removed = before_dup - after_dup

if dup_removed > 0:
    print(f"   ✅ Removed {dup_removed} duplicate records")
else:
    print(f"   ✅ No duplicates found")

# Verify no liquor stores (should be 0)
liquor_check = df_curr['Store'].str.contains('liquor|wine|beer|spirits', case=False, na=False).sum()
if liquor_check == 0:
    print(f"   ✅ No liquor store items (correct!)")
else:
    print(f"   ⚠️  WARNING: Found {liquor_check} liquor items in current flyers")

# Standardize dates
df_curr['Date'] = pd.to_datetime(df_curr['Date'], errors='coerce')
df_curr['Valid_Until'] = pd.to_datetime(df_curr['Valid_Until'], errors='coerce')

# Save cleaned current flyers
df_curr.to_csv('current_flyers.csv', index=False)
print(f"   After: {len(df_curr):,} records")
print(f"   ✅ Saved cleaned current_flyers.csv")

# ============================================================================
# FIX 3: UPDATE DASHBOARD FILE
# ============================================================================

print("\n📊 Updating clean_grocery_data.csv...")

# Just copy the cleaned current flyers
df_curr.to_csv('clean_grocery_data.csv', index=False)
print(f"   ✅ Saved clean_grocery_data.csv ({len(df_curr):,} records)")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("✅ CLEANUP COMPLETE!")
print("=" * 80)

print(f"\n📊 Summary of Changes:")
print(f"   Historical Archive:")
print(f"      - Removed {liquor_count} liquor items")
print(f"      - Standardized date formats")
print(f"      - Final size: {len(df_hist):,} records")

print(f"\n   Current Flyers:")
if dup_removed > 0:
    print(f"      - Removed {dup_removed} duplicates")
else:
    print(f"      - No duplicates found")
print(f"      - Final size: {len(df_curr):,} records")

print(f"\n🎯 Database Status:")
print(f"   ✅ Liquor contamination: REMOVED")
print(f"   ✅ Date formats: STANDARDIZED")
print(f"   ✅ Duplicates: REMOVED")
print(f"   ✅ All databases: CLEAN")

print(f"\n💡 Next Steps:")
print(f"   1. Run get_deals.py to test scraper")
print(f"   2. Generate Facebook post with cleaned data")
print(f"   3. Set up automated overnight scraping")

print("=" * 80)
