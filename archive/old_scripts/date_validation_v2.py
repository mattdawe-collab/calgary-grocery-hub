"""
IMPROVED Date Validation for get_deals.py
Handles missing dates more intelligently
"""

import pandas as pd
from datetime import timedelta

def validate_and_fix_dates_v2(df):
    """
    Smarter date validation:
    1. Only fix dates that are clearly wrong (before scrape date)
    2. Don't blindly add 7 days to missing dates
    3. Log which stores have issues
    """
    today = pd.Timestamp.now().floor('D')
    
    # Convert to datetime
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Valid_Until'] = pd.to_datetime(df['Valid_Until'], errors='coerce')
    
    # Fix 1: If valid_until is BEFORE the scrape date, it's definitely wrong
    mask_past = df['Valid_Until'] < df['Date']
    if mask_past.sum() > 0:
        stores_affected = df.loc[mask_past, 'Store'].unique()
        print(f"   🔧 Fixed {mask_past.sum()} deals with expiry before scrape date")
        print(f"      Affected stores: {', '.join(stores_affected)}")
        df.loc[mask_past, 'Valid_Until'] = df.loc[mask_past, 'Date'] + timedelta(days=7)
    
    # Fix 2: For missing dates, DON'T automatically add 7 days
    # Instead, flag them for manual review
    mask_missing = df['Valid_Until'].isna()
    if mask_missing.sum() > 0:
        stores_missing = df.loc[mask_missing, 'Store'].unique()
        print(f"   ⚠️  WARNING: {mask_missing.sum()} deals have missing expiry dates")
        print(f"      Affected stores: {', '.join(stores_missing)}")
        print(f"      These may need manual correction - check flyer sources!")
        
        # For now, use a conservative 3-day window instead of 7
        # (Most weekly flyers end mid-week)
        df.loc[mask_missing, 'Valid_Until'] = df.loc[mask_missing, 'Date'] + timedelta(days=3)
        print(f"      Temporarily set to scrape_date + 3 days for safety")
    
    # Fix 3: If date is in the future, set to today
    mask_future = df['Date'] > today
    if mask_future.sum() > 0:
        print(f"   🔧 Fixed {mask_future.sum()} deals with future scrape dates")
        df.loc[mask_future, 'Date'] = today
    
    # Info: Report on date distribution
    print(f"\n   📅 Expiry Date Summary:")
    date_counts = df.groupby('Valid_Until')['Item'].count().sort_index()
    for date, count in date_counts.items():
        days_away = (date - today).days
        status = "✅" if days_away >= 0 else "❌ EXPIRED"
        print(f"      {date.strftime('%b %d')}: {count} deals ({days_away} days from now) {status}")
    
    expired = (df['Valid_Until'] < today).sum()
    if expired > 0:
        print(f"\n   ⚠️  {expired} deals are already expired and will be filtered out by dashboard")
    
    return df


"""
INTEGRATION INSTRUCTIONS:
=========================

In get_deals.py, replace the validate_and_fix_dates() function with 
validate_and_fix_dates_v2() above.

This version:
- Only adds days when dates are clearly wrong (before scrape date)
- Uses 3 days instead of 7 for missing dates (more conservative)
- Provides detailed logging so you can see which stores have issues
- Shows a summary of all expiry dates

If Superstore consistently has missing dates, you may need to:
1. Check if the flyer API returns valid_to at the flyer level
2. Manually inspect the flyer source data
3. Add store-specific logic for known issues
"""
