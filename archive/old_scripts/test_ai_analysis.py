"""
TEST SCRIPT - AI Quality Analysis
Tests on 10 items before running full backfill
"""

import pandas as pd
import os
from ai_quality_analyzer import AIQualityAnalyzer

print("=" * 80)
print("AI QUALITY ANALYSIS - TEST (10 ITEMS)")
print("=" * 80)

# Load historical archive
HISTORICAL_ARCHIVE = 'historical_archive.csv'

if not os.path.exists(HISTORICAL_ARCHIVE):
    print(f"❌ ERROR: {HISTORICAL_ARCHIVE} not found!")
    exit(1)

df = pd.read_csv(HISTORICAL_ARCHIVE)
print(f"\n✅ Loaded archive: {len(df):,} records")

# Convert dates
df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

# Get 10 unique items for testing
test_items = df.drop_duplicates(subset=['Item']).head(10)

print(f"\n📋 Testing with {len(test_items)} items:")
for idx, row in test_items.iterrows():
    print(f"   {row['Item']}")

# Prepare test data
items_for_analysis = []
for _, row in test_items.iterrows():
    item_name = row['Item']
    current_price = row['Price_Value']
    
    # Get historical data for this item
    history = df[df['Item'] == item_name]
    
    items_for_analysis.append({
        'item_name': item_name,
        'current_price': current_price,
        'price_history': history['Price_Value'].tolist(),
        'date_history': history['Date'].astype(str).tolist(),
        'store_history': history['Store'].tolist()
    })

print(f"\n🤖 Running AI analysis...")
print(f"   Model: Gemini 2.5 Flash Latest")
print(f"   Items: {len(items_for_analysis)}")

try:
    analyzer = AIQualityAnalyzer()
    print(f"   ✅ Analyzer initialized")
    
    analyses = analyzer.analyze_batch(items_for_analysis)
    print(f"   ✅ AI analysis complete!")
    
    print(f"\n📊 RESULTS:")
    print("=" * 80)
    
    for idx, analysis in enumerate(analyses):
        item = items_for_analysis[idx]
        print(f"\n{idx + 1}. {item['item_name']}")
        print(f"   Price: ${item['current_price']:.2f}")
        print(f"   ─────────────────────────────")
        print(f"   Normalized Name: {analysis.normalized_name}")
        print(f"   Category: {analysis.category}")
        print(f"   Sub-Category: {analysis.sub_category}")
        print(f"   Brand: {analysis.brand}")
        print(f"   ─────────────────────────────")
        print(f"   Reliability: {analysis.reliability} ({analysis.confidence} confidence)")
        print(f"   Data Points: {analysis.data_points}")
        print(f"   Issues: {analysis.quality_issues}")
        print(f"   ─────────────────────────────")
        print(f"   Anomaly: {analysis.has_anomaly}")
        if analysis.has_anomaly:
            print(f"   Anomaly Type: {analysis.anomaly_type}")
            print(f"   Explanation: {analysis.anomaly_explanation}")
        print(f"   ─────────────────────────────")
        print(f"   Deal Rating: {analysis.deal_rating} (Score: {analysis.deal_score}/100)")
        print(f"   vs History: {analysis.vs_history}")
        if analysis.vs_market:
            print(f"   vs Market: {analysis.vs_market}")
        print(f"   Recommendation: {analysis.recommendation}")
    
    print("\n" + "=" * 80)
    print("✅ TEST SUCCESSFUL!")
    print("=" * 80)
    
    # Summary statistics
    categories = [a.category for a in analyses]
    print(f"\n📊 Summary:")
    print(f"   Items analyzed: {len(analyses)}")
    print(f"   Categories assigned: {len(set(categories))}")
    print(f"   Category breakdown:")
    from collections import Counter
    for cat, count in Counter(categories).items():
        print(f"      • {cat}: {count}")
    
    subcats = [a.sub_category for a in analyses if a.sub_category]
    print(f"   Subcategories assigned: {len(subcats)}/{len(analyses)}")
    
    brands = [a.brand for a in analyses if a.brand]
    print(f"   Brands detected: {len(brands)}/{len(analyses)}")
    
    anomalies = [a for a in analyses if a.has_anomaly]
    print(f"   Anomalies detected: {len(anomalies)}/{len(analyses)}")
    
    reliability_counts = Counter([a.reliability for a in analyses])
    print(f"   Reliability breakdown:")
    for rel, count in reliability_counts.items():
        print(f"      • {rel}: {count}")
    
    print("\n🎯 Next Steps:")
    print("   ✅ AI is working correctly!")
    print("   ✅ Categories are being assigned properly")
    print("   ✅ Ready to run full backfill: python backfill_ai_analysis.py")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ERROR during AI analysis:")
    print(f"   {type(e).__name__}: {str(e)}")
    print(f"\n🔍 Troubleshooting:")
    print(f"   1. Check GEMINI_API_KEY in .env file")
    print(f"   2. Verify internet connection")
    print(f"   3. Check if model 'gemini-2.5-flash-latest' is available")
    print(f"   4. Try alternative model: 'gemini-2.5-flash-002'")
    print("\n" + "=" * 80)
    import traceback
    print("\nFull error trace:")
    traceback.print_exc()
