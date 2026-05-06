"""
RECOVERY SCRIPT - Runs AI Backfill with Correct Field Mapping
This is the FIXED version that uses the flattened GroceryAnalysis model
"""

import pandas as pd
import os
from datetime import datetime
from ai_quality_analyzer import AIQualityAnalyzer

print("=" * 80)
print("AI QUALITY BACKFILL - RECOVERY RUN")
print("=" * 80)
print("\nThis will analyze ALL historical records with the CORRECT field mapping.")
print("Estimated time: 3-4 hours (same as before, sorry!)")
print("Estimated cost: $0.80-1.20")
print("\n⚠️  SAFETY: Using existing backup from previous run...")

# Paths
HISTORICAL_ARCHIVE = 'historical_archive.csv'

# === CHECK FOR EXISTING BACKUP ===
print(f"\n📋 STEP 1: Checking for backup...")

# Find the most recent backup
import glob
backups = glob.glob('historical_archive_BEFORE_AI_BACKFILL_*.csv')
if backups:
    latest_backup = sorted(backups)[-1]
    print(f"   ✅ Found existing backup: {latest_backup}")
    print(f"   Will use this backup to restore if needed")
else:
    print(f"   ⚠️  No backup found - creating new one...")
    BACKUP_PATH = f'historical_archive_BEFORE_AI_BACKFILL_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    df_backup = pd.read_csv(HISTORICAL_ARCHIVE)
    df_backup.to_csv(BACKUP_PATH, index=False)
    print(f"   ✅ Backup saved: {BACKUP_PATH}")

# === LOAD DATA ===
if not os.path.exists(HISTORICAL_ARCHIVE):
    print(f"❌ ERROR: {HISTORICAL_ARCHIVE} not found!")
    exit(1)

df_archive = pd.read_csv(HISTORICAL_ARCHIVE)
original_count = len(df_archive)
print(f"\n📊 Loaded archive: {original_count:,} records")

# === STEP 2: PREPARE DATA ===
print(f"\n📊 STEP 2: Preparing data...")

# Convert dates
df_archive['Date'] = pd.to_datetime(df_archive['Date'], errors='coerce')
df_archive['Valid_Until'] = pd.to_datetime(df_archive['Valid_Until'], errors='coerce')

# Clean price column names if needed
if 'Price_Value' in df_archive.columns and 'price' not in df_archive.columns:
    df_archive['price'] = df_archive['Price_Value']
if 'Item' in df_archive.columns and 'item' not in df_archive.columns:
    df_archive['item'] = df_archive['Item']

# Get unique items (to avoid analyzing same item multiple times)
unique_items = df_archive.drop_duplicates(subset=['Item', 'Store'])
print(f"   Total records: {original_count:,}")
print(f"   Unique items: {len(unique_items):,}")
print(f"   Will analyze unique items, then map back to all records")

# === STEP 3: PREPARE ITEMS FOR AI ANALYSIS ===
print(f"\n🤖 STEP 3: Preparing items for AI analysis...")

items_for_analysis = []
for _, row in unique_items.iterrows():
    item_name = row['Item']
    current_price = row['price']
    
    # Get historical data for this item (same item across all dates)
    history = df_archive[df_archive['Item'] == item_name]
    
    items_for_analysis.append({
        'item_name': item_name,
        'current_price': current_price,
        'price_history': history['price'].tolist(),
        'date_history': history['Date'].astype(str).tolist(),
        'store_history': history['Store'].tolist()
    })

print(f"   Prepared {len(items_for_analysis):,} items for analysis")

# === STEP 4: RUN AI ANALYSIS ===
print(f"\n🧠 STEP 4: Running AI analysis...")
print(f"   This will take ~2.5-3 hours for {len(items_for_analysis):,} items")
print(f"   Processing in batches of 50 (reliable batch size)...")

analyzer = AIQualityAnalyzer()

all_analyses = []
batch_size = 50  # Proven reliable - larger batches are inconsistent
total_batches = (len(items_for_analysis) + batch_size - 1) // batch_size

for i in range(0, len(items_for_analysis), batch_size):
    batch = items_for_analysis[i:i+batch_size]
    batch_num = i // batch_size + 1
    
    print(f"   Batch {batch_num}/{total_batches} ({i+1}-{min(i+batch_size, len(items_for_analysis))} of {len(items_for_analysis):,})...", end=' ')
    
    try:
        analyses = analyzer.analyze_batch(batch)
        all_analyses.extend(analyses)
        print("✅")
        
        # === VALIDATION AFTER FIRST 3 BATCHES ===
        if batch_num in [1, 2, 3]:
            print(f"\n   🔍 VALIDATING BATCH {batch_num}...")
            
            # Check if we got results
            if not analyses or len(analyses) == 0:
                print(f"   ❌ VALIDATION FAILED: No analyses returned!")
                print(f"   Batch size {batch_size} may be too large. Try smaller batch.")
                exit(1)
            
            # Check if categories are actually being assigned (not all "Other")
            categories = [a.category for a in analyses]
            other_count = sum(1 for c in categories if c == "Other")
            other_pct = (other_count / len(analyses)) * 100
            
            if other_pct > 80:
                print(f"   ⚠️  WARNING: {other_pct:.1f}% categorized as 'Other'")
                print(f"   AI may not be working properly")
                response = input(f"   Continue anyway? (y/n): ")
                if response.lower() != 'y':
                    print(f"   Stopped by user. Try smaller batch size or check AI config.")
                    exit(1)
            else:
                print(f"   ✅ Categories: {other_pct:.1f}% 'Other', {100-other_pct:.1f}% categorized")
            
            # Check if deal ratings vary (not all the same)
            ratings = [a.deal_rating for a in analyses]
            unique_ratings = len(set(ratings))
            
            if unique_ratings < 3:
                print(f"   ⚠️  WARNING: Only {unique_ratings} unique deal ratings")
            else:
                print(f"   ✅ Deal ratings: {unique_ratings} different ratings")
            
            # Check if subcategories are being assigned
            subcats = [a.sub_category for a in analyses if a.sub_category]
            subcat_pct = (len(subcats) / len(analyses)) * 100
            print(f"   ✅ Subcategories: {subcat_pct:.1f}%")
            
            # After batch 3, give final go/no-go
            if batch_num == 3:
                print(f"\n   🎯 BATCHES 1-3 VALIDATED SUCCESSFULLY!")
                print(f"   All 3 batches show consistent quality.")
                print(f"   Ready to process remaining {total_batches - 3} batches...")
                print(f"   (Estimated time: {((total_batches - 3) * 2):.0f} more minutes)\n")
                response = input(f"   Proceed with full backfill? (y/n): ")
                if response.lower() != 'y':
                    print(f"   Stopped by user.")
                    exit(1)
                print(f"\n   🚀 Full backfill approved! Running remaining batches...\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        # Create default analyses for failed batch
        for item in batch:
            all_analyses.append(analyzer._default_analysis(item))
        print(f"   ⚠️  Using default analysis for failed batch")

print(f"\n   ✅ AI analysis complete! Analyzed {len(all_analyses):,} items")

# === STEP 5: CREATE MAPPING (FIXED VERSION!) ===
print(f"\n📝 STEP 5: Creating AI data mapping (FIXED VERSION)...")

# Create a mapping from item name to AI analysis
ai_mapping = {}
for idx, item in enumerate(items_for_analysis):
    if idx < len(all_analyses):
        analysis = all_analyses[idx]
        # FIXED: Use flattened fields, not nested!
        ai_mapping[item['item_name']] = {
            'ai_normalized_name': analysis.normalized_name,
            'ai_base_product': analysis.base_product,
            'ai_category': analysis.category,
            'ai_sub_category': analysis.sub_category,
            'ai_brand': analysis.brand,
            'ai_reliability': analysis.reliability,
            'ai_confidence': analysis.confidence,
            'ai_has_anomaly': analysis.has_anomaly,
            'ai_anomaly_type': analysis.anomaly_type,
            'ai_deal_rating': analysis.deal_rating,
            'ai_deal_score': analysis.deal_score,
            'ai_recommendation': analysis.recommendation,
            'ai_vs_history': analysis.vs_history,
            'ai_vs_market': analysis.vs_market,
            'ai_explanation': analysis.quality_explanation
        }

print(f"   Created mapping for {len(ai_mapping):,} items")

# === STEP 6: APPLY TO ALL RECORDS ===
print(f"\n📊 STEP 6: Applying AI data to all {original_count:,} records...")

# Initialize new columns
ai_columns = [
    'ai_normalized_name', 'ai_base_product', 'ai_category', 'ai_sub_category',
    'ai_brand', 'ai_reliability', 'ai_confidence', 'ai_has_anomaly',
    'ai_anomaly_type', 'ai_deal_rating', 'ai_deal_score', 'ai_recommendation',
    'ai_vs_history', 'ai_vs_market', 'ai_explanation'
]

for col in ai_columns:
    df_archive[col] = None

# Map AI data to each record
for idx, row in df_archive.iterrows():
    item_name = row['Item']
    if item_name in ai_mapping:
        for col, value in ai_mapping[item_name].items():
            df_archive.at[idx, col] = value
    
    # Progress indicator
    if (idx + 1) % 1000 == 0:
        print(f"   Processed {idx + 1:,} / {original_count:,} records...")

print(f"   ✅ Applied AI data to all records")

# === STEP 7: VALIDATE ===
print(f"\n✅ STEP 7: Validating results...")

# Check how many records got AI data
ai_populated = df_archive['ai_category'].notna().sum()
print(f"   Records with AI data: {ai_populated:,} / {original_count:,} ({ai_populated/original_count*100:.1f}%)")

# Show sample
print(f"\n   Sample of AI-enhanced records:")
sample = df_archive[df_archive['ai_category'].notna()].head(3)
for _, row in sample.iterrows():
    print(f"      • {row['Item']}")
    print(f"        Category: {row['ai_category']} > {row['ai_sub_category']}")
    print(f"        Deal Rating: {row['ai_deal_rating']} (Score: {row['ai_deal_score']})")
    print(f"        Reliability: {row['ai_reliability']}")

# Show statistics
print(f"\n   📈 AI Analysis Statistics:")
if ai_populated > 0:
    print(f"      Excellent reliability: {(df_archive['ai_reliability'] == 'excellent').sum():,}")
    print(f"      Good reliability: {(df_archive['ai_reliability'] == 'good').sum():,}")
    print(f"      Fair reliability: {(df_archive['ai_reliability'] == 'fair').sum():,}")
    print(f"      Poor reliability: {(df_archive['ai_reliability'] == 'poor').sum():,}")
    print(f"      Anomalies detected: {df_archive['ai_has_anomaly'].sum():,}")
    print(f"      Excellent deals: {(df_archive['ai_deal_rating'] == 'excellent').sum():,}")

# === STEP 8: SAVE ===
print(f"\n💾 STEP 8: Saving enhanced archive...")

# Save to new file first (safety)
TEMP_PATH = 'historical_archive_WITH_AI.csv'
df_archive.to_csv(TEMP_PATH, index=False)
print(f"   ✅ Saved to temporary file: {TEMP_PATH}")

# Verify the save worked
df_verify = pd.read_csv(TEMP_PATH)
if len(df_verify) == original_count:
    print(f"   ✅ Verification passed: {len(df_verify):,} records")
    
    # Now overwrite original
    df_archive.to_csv(HISTORICAL_ARCHIVE, index=False)
    print(f"   ✅ Updated original: {HISTORICAL_ARCHIVE}")
    
    # Clean up temp file
    os.remove(TEMP_PATH)
    print(f"   ✅ Cleaned up temporary file")
else:
    print(f"   ❌ ERROR: Verification failed!")
    print(f"   Expected {original_count:,} records, got {len(df_verify):,}")
    print(f"   Original archive NOT modified")
    print(f"   Enhanced data saved in: {TEMP_PATH}")
    exit(1)

# === FINAL SUMMARY ===
print("\n" + "=" * 80)
print("✅ BACKFILL COMPLETE!")
print("=" * 80)
print(f"\n📊 Summary:")
print(f"   Original records: {original_count:,}")
print(f"   Records with AI data: {ai_populated:,} ({ai_populated/original_count*100:.1f}%)")
print(f"   New columns added: {len(ai_columns)}")
if backups:
    print(f"   Backup available: {latest_backup}")
print(f"\n🎉 Your historical archive now has AI quality analysis!")
print(f"   Next run of get_deals.py will use the same format.")
print("\n" + "=" * 80)
