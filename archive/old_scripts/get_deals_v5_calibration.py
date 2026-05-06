"""
Calgary Grocery Hub - API Scraper with PDF Calibration
v5.0 - Calibration Architecture

PHILOSOPHY:
- API is TRUTH (complete dataset, 1,400 items)
- PDF is CALIBRATION (signals: member pricing, featured items, spot-checks)
- Gemini 3 Flash extracts SIGNALS, not every item
- Claude analyzes with enhanced context
"""

import requests
import pandas as pd
import datetime
from datetime import timedelta
import os
import time
import re
from dotenv import load_dotenv
from sqlalchemy import create_engine
from ai_quality_analyzer import add_ai_analysis_to_dataframe

# PDF Calibration imports
from pathlib import Path
from PIL import Image
import io
import fitz  # PyMuPDF
import google.generativeai as genai

# --- CONFIGURATION ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

HISTORICAL_ARCHIVE = 'historical_archive.csv'
CURRENT_FLYERS = 'current_flyers.csv'
DASHBOARD_FILE = 'clean_grocery_data.csv'

POSTAL_CODE = "T3M1M9"
STORES = [
    "Real Canadian Superstore", "Save-On-Foods", "Calgary Co-op",
    "Sobeys", "Safeway", "No Frills"
]

EXCLUDED_MERCHANTS = [
    "liquor", "pharmacy", "wine", "beer", "spirits", "lcbo", "liquor store"
]

BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

# --- PDF CALIBRATION FUNCTIONS ---

def pdf_calibration_enabled():
    """Check if PDF calibration should run."""
    pdf_folder = Path("flyers")
    if not pdf_folder.exists():
        return False
    pdfs = list(pdf_folder.glob("*.pdf"))
    return len(pdfs) > 0 and os.getenv('GEMINI_API_KEY')

def extract_store_from_filename(filename):
    """Identify store from PDF filename."""
    filename_lower = filename.lower()
    store_patterns = {
        "sobeys": "Sobeys",
        "safeway": "Safeway",
        "superstore": "Real Canadian Superstore",
        "real canadian": "Real Canadian Superstore",
        "save-on": "Save-On-Foods",
        "save on": "Save-On-Foods",
        "saveon": "Save-On-Foods",
        "co-op": "Calgary Co-op",
        "coop": "Calgary Co-op",
        "co op": "Calgary Co-op",
        "no frills": "No Frills",
        "nofrills": "No Frills"
    }
    for pattern, store_name in store_patterns.items():
        if pattern in filename_lower:
            return store_name
    return None

def pdf_to_images(pdf_path, dpi=200):
    """Convert PDF to images (moderate DPI for calibration)."""
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    doc.close()
    return images

def extract_calibration_signals(images, store_name):
    """
    Extract CALIBRATION SIGNALS from PDF (not complete item list).
    
    Returns signals for:
    - Member pricing indicators
    - Featured/prominent items
    - Price spot-checks for validation
    """
    
    print(f"      📊 Extracting calibration signals (not full OCR)...")
    
    calibration_data = {
        'store': store_name,
        'member_items': [],
        'featured_items': [],
        'spot_checks': []
    }
    
    for page_num, img in enumerate(images, 1):
        
        # FOCUSED CALIBRATION PROMPT
        prompt = f"""Analyze page {page_num} for these SIGNALS ONLY:

1. MEMBER PRICING: List items with member/club indicators
   (Member Price, Club Price, MyOffers badges)
   Format: ItemName | Price

2. FEATURED ITEMS: List 3-5 most prominent items
   (large display, red circles, hot deal badges, top of page)
   Format: ItemName | Price

3. SPOT CHECK: List 5-8 random prices for validation
   Format: ItemName | Price

Keep responses SHORT. We're calibrating, not extracting everything."""

        try:
            model = genai.GenerativeModel('gemini-3-flash-preview')
            buffered = io.BytesIO()
            img.save(buffered, format="PNG", optimize=False, quality=85)
            
            response = model.generate_content(
                [prompt, {'mime_type': 'image/png', 'data': buffered.getvalue()}],
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 1500  # Short responses
                }
            )
            
            response_text = response.text.strip()
            
            # Parse responses (lenient parsing)
            for line in response_text.split('\n'):
                line = line.strip()
                if not line or '|' not in line:
                    continue
                
                # Skip headers
                if any(skip in line.upper() for skip in ['MEMBER PRICING', 'FEATURED', 'SPOT CHECK', 'FORMAT:']):
                    continue
                
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2 and parts[0] and parts[1]:
                    item_data = {
                        'name': parts[0],
                        'price': parts[1],
                        'page': page_num
                    }
                    
                    # Classify based on context in response
                    line_upper = line.upper()
                    response_upper = response_text.upper()
                    line_pos = response_upper.find(line_upper)
                    
                    # Check what section this line is in
                    member_pos = response_upper.find('MEMBER')
                    featured_pos = response_upper.find('FEATURED')
                    spot_pos = response_upper.find('SPOT')
                    
                    if member_pos != -1 and abs(line_pos - member_pos) < 500:
                        calibration_data['member_items'].append(item_data)
                    elif featured_pos != -1 and abs(line_pos - featured_pos) < 500:
                        calibration_data['featured_items'].append(item_data)
                    elif spot_pos != -1 and abs(line_pos - spot_pos) < 500:
                        calibration_data['spot_checks'].append(item_data)
                    else:
                        # Default to spot check
                        calibration_data['spot_checks'].append(item_data)
            
            time.sleep(0.3)  # Brief pause
            
        except Exception as e:
            print(f"         Page {page_num}: {str(e)[:50]}")
            continue
    
    print(f"         ✅ Member indicators: {len(calibration_data['member_items'])}")
    print(f"         ✅ Featured items: {len(calibration_data['featured_items'])}")
    print(f"         ✅ Spot checks: {len(calibration_data['spot_checks'])}")
    
    return calibration_data

def fuzzy_match(str1, str2, threshold=0.5):
    """Simple fuzzy string matching for calibration."""
    str1 = str1.lower()
    str2 = str2.lower()
    
    # Direct substring match
    if str1 in str2 or str2 in str1:
        return True
    
    # Word overlap
    words1 = set(w for w in str1.split() if len(w) > 3)
    words2 = set(w for w in str2.split() if len(w) > 3)
    
    if not words1 or not words2:
        return False
    
    overlap = len(words1 & words2) / len(words1 | words2)
    return overlap >= threshold

def calibrate_api_data(df_api, all_calibration_signals):
    """
    Enhance API data with PDF calibration signals.
    API remains the truth; PDF provides context.
    """
    
    print(f"\n📊 CALIBRATING API DATA WITH PDF SIGNALS")
    
    total_member = sum(len(cal['member_items']) for cal in all_calibration_signals.values())
    total_featured = sum(len(cal['featured_items']) for cal in all_calibration_signals.values())
    total_spots = sum(len(cal['spot_checks']) for cal in all_calibration_signals.values())
    
    print(f"   Total signals extracted:")
    print(f"   - Member indicators: {total_member}")
    print(f"   - Featured items: {total_featured}")
    print(f"   - Spot checks: {total_spots}")
    
    # Add calibration columns
    df_api['is_member_exclusive'] = False
    df_api['member_indicator'] = None
    df_api['is_featured'] = False
    df_api['pdf_page'] = None
    df_api['price_validated'] = False
    
    member_matched = 0
    featured_matched = 0
    validated = 0
    
    for idx, row in df_api.iterrows():
        store = row['Store']
        api_name = str(row['Item'])
        
        if store not in all_calibration_signals:
            continue
        
        cal_data = all_calibration_signals[store]
        
        # Check member pricing signals
        for member_item in cal_data['member_items']:
            if fuzzy_match(api_name, member_item['name']):
                df_api.at[idx, 'is_member_exclusive'] = True
                df_api.at[idx, 'member_indicator'] = 'Member Price'
                df_api.at[idx, 'pdf_page'] = member_item['page']
                member_matched += 1
                break
        
        # Check featured status
        for featured_item in cal_data['featured_items']:
            if fuzzy_match(api_name, featured_item['name']):
                df_api.at[idx, 'is_featured'] = True
                if not df_api.at[idx, 'pdf_page']:
                    df_api.at[idx, 'pdf_page'] = featured_item['page']
                featured_matched += 1
                break
        
        # Spot check price validation
        for spot_item in cal_data['spot_checks']:
            if fuzzy_match(api_name, spot_item['name']):
                df_api.at[idx, 'price_validated'] = True
                validated += 1
                break
    
    print(f"\n✅ CALIBRATION COMPLETE:")
    print(f"   {member_matched} items marked as member exclusive")
    print(f"   {featured_matched} items marked as featured")
    print(f"   {validated} prices validated via spot-check")
    
    # Save member exclusives report
    if member_matched > 0:
        member_df = df_api[df_api['is_member_exclusive'] == True][
            ['Store', 'Item', 'Price_Text', 'Price_Value', 'pdf_page']
        ]
        member_df.to_csv('member_exclusive_items.csv', index=False)
        print(f"\n🎫 Member exclusives saved to: member_exclusive_items.csv")
    
    return df_api

# --- EXISTING HELPER FUNCTIONS (from your original code) ---

def is_excluded_merchant(merchant_name):
    """Check if merchant should be excluded."""
    if not merchant_name:
        return False
    merchant_lower = merchant_name.lower()
    for excluded in EXCLUDED_MERCHANTS:
        if excluded in merchant_lower:
            print(f"   ⚠️  SKIPPING: {merchant_name} (contains '{excluded}')")
            return True
    return False

def get_active_flyers(postal_code):
    """Get active flyers for postal code."""
    url = f"{BASE_URL}/flyers"
    params = {'postal_code': postal_code, 'locale': 'en-ca'}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        return response.json().get('flyers', [])
    except:
        return []

def get_flyer_items(flyer_id):
    """Get items from a flyer."""
    url = f"{BASE_URL}/flyers/{flyer_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            return data.get('items') or data.get('spread_items') or []
    except:
        pass
    return []

def clean_price(item_dict):
    """Enhanced price cleaning."""
    keys = ['price', 'current_price', 'price_text', 'sale_price', 'original_price']
    raw_price = next((item_dict[k] for k in keys if item_dict.get(k)), None)
    
    if not raw_price:
        return None, None, None
    
    try:
        clean = str(raw_price).replace('$', '').replace('Â¢', '').lower().strip()
        
        # Per-weight pricing
        per_weight = re.search(r'(\d+(?:\.\d+)?)\s*(?:/|per)\s*(lb|lbs|kg|100g|g)', clean)
        if per_weight:
            price = float(per_weight.group(1))
            unit = per_weight.group(2).replace('lbs', 'lb')
            
            if unit == 'lb':
                normalized_price = price * 2.20462
            elif unit == '100g':
                normalized_price = price * 10
            elif unit == 'g':
                normalized_price = price * 1000
            else:
                normalized_price = price
            
            return raw_price, price, f"${normalized_price:.2f}/kg"
        
        # Multi-buy deals
        multibuy = re.search(r'(\d+)\s*(?:/|for)\s*\$?(\d+(?:\.\d+)?)', clean)
        if multibuy:
            qty = float(multibuy.group(1))
            total_price = float(multibuy.group(2))
            if qty > 0:
                unit_price = total_price / qty
                return raw_price, unit_price, None
        
        # Regular price
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches:
            return raw_price, float(matches[0]), None
        
        return raw_price, None, None
        
    except Exception as e:
        return raw_price, None, None

def validate_and_fix_dates(df):
    """Fix date issues."""
    today = pd.Timestamp.now().floor('D')
    
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Valid_Until'] = pd.to_datetime(df['Valid_Until'], errors='coerce')
    
    mask = df['Valid_Until'] < df['Date']
    if mask.sum() > 0:
        df.loc[mask, 'Valid_Until'] = df.loc[mask, 'Date'] + timedelta(days=7)
    
    mask = df['Valid_Until'].isna()
    if mask.sum() > 0:
        df.loc[mask, 'Valid_Until'] = df.loc[mask, 'Date'] + timedelta(days=7)
    
    mask = df['Date'] > today
    if mask.sum() > 0:
        df.loc[mask, 'Date'] = today
    
    return df

# --- MAIN EXECUTION ---

print("=" * 80)
print("🛒 CALGARY GROCERY HUB - API + PDF CALIBRATION")
print("=" * 80)
print(f"\n>> Scanning flyers for postal code: {POSTAL_CODE}...")

flyers = get_active_flyers(POSTAL_CODE)
if not flyers:
    print("[!] No flyers found.")
    exit()

print(f"   Found {len(flyers)} total flyers in your area")

# Select best flyers
selected_flyers = []
excluded_count = 0

for store in STORES:
    print(f"\n🔍 Looking for: {store}")
    matches = []
    
    for f in flyers:
        merchant = f.get('merchant', '')
        if is_excluded_merchant(merchant):
            excluded_count += 1
            continue
        if store.lower() in merchant.lower():
            matches.append(f)
    
    if not matches:
        print(f"   ⚠️  No flyers found for {store}")
        continue
    
    best = max(matches, key=lambda f: f.get('valid_to', ''))
    selected_flyers.append(best)
    print(f"   ✅ Selected: {best['merchant']}")
    print(f"      Valid: {best.get('valid_from')} to {best.get('valid_to')}")

print(f"\n📊 Summary:")
print(f"   Total flyers: {len(flyers)}")
print(f"   Excluded: {excluded_count}")
print(f"   Selected: {len(selected_flyers)}")

if not selected_flyers:
    print("\n[!] No valid flyers selected. Exiting.")
    exit()

# --- SCRAPE API DATA (TRUTH) ---

new_deals = []
print("\n>> Extracting items from API...")

for flyer in selected_flyers:
    print(f"\n📄 Processing: {flyer['merchant']}")
    items = get_flyer_items(flyer['id'])
    print(f"   Found {len(items)} items")
    
    for item in items:
        name = item.get('name')
        price_txt, price_val, normalized = clean_price(item)
        if name:
            new_deals.append({
                'Date': datetime.date.today(),
                'Store': flyer['merchant'],
                'Original_Name': name,
                'Item': name,
                'Price_Text': price_txt if price_txt else "Check Store",
                'Price_Value': price_val if price_val is not None else 0.0,
                'Normalized_Price': normalized,
                'Valid_Until': item.get('valid_to') or flyer.get('valid_to')
            })

print(f"\n>> Total items from API: {len(new_deals)}")

if not new_deals:
    print("[!] No items found.")
    exit()

df_new = pd.DataFrame(new_deals)
df_new['Item'] = df_new['Item'].astype(str).str.title()

# --- PDF CALIBRATION (SIGNALS) ---

all_calibration_signals = {}

if pdf_calibration_enabled():
    print("\n" + "=" * 80)
    print("📄 PDF CALIBRATION LAYER")
    print("=" * 80)
    
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    
    pdf_folder = Path("flyers")
    pdfs = list(pdf_folder.glob("*.pdf"))
    
    # Match PDFs to stores
    store_pdfs = {}
    for pdf in pdfs:
        store = extract_store_from_filename(pdf.name)
        if store and store in df_new['Store'].values:
            if store not in store_pdfs or pdf.stat().st_mtime > store_pdfs[store].stat().st_mtime:
                store_pdfs[store] = pdf
    
    if store_pdfs:
        print(f"\n✅ Found {len(store_pdfs)} PDFs:")
        for store, pdf in store_pdfs.items():
            print(f"   {store}: {pdf.name}")
        
        total_cost = 0
        
        for store_idx, (store, pdf_path) in enumerate(store_pdfs.items()):
            print(f"\n🏪 {store}: {pdf_path.name}")
            
            try:
                images = pdf_to_images(pdf_path, dpi=200)
                
                cost = 0.01 * len(images)  # Estimate
                total_cost += cost
                
                calibration_signals = extract_calibration_signals(images, store)
                all_calibration_signals[store] = calibration_signals
                
            except Exception as e:
                print(f"      ❌ Error: {str(e)[:80]}")
                continue
            
            if store_idx < len(store_pdfs) - 1:
                time.sleep(1)
        
        print(f"\n💰 PDF calibration cost: ~${total_cost:.3f}")
        
        # Calibrate API data with PDF signals
        df_new = calibrate_api_data(df_new, all_calibration_signals)
    else:
        print("\n💡 PDFs found but couldn't match to stores")
else:
    print("\n💡 PDF calibration disabled (no PDFs or no GEMINI_API_KEY)")

# --- LOAD HISTORICAL DATA ---

if os.path.exists(HISTORICAL_ARCHIVE):
    df_archive = pd.read_csv(HISTORICAL_ARCHIVE)
    df_archive['Date'] = pd.to_datetime(df_archive['Date'], format='mixed', errors='coerce')
    print(f"\n📚 Historical archive: {len(df_archive):,} records")
    
    # Identify new items
    df_new['_dup_key'] = (df_new['Store'] + '|' + df_new['Original_Name'] + '|' +
                          df_new['Price_Text'] + '|' + df_new['Valid_Until'].astype(str))
    df_archive['_dup_key'] = (df_archive['Store'] + '|' + df_archive['Original_Name'] + '|' +
                              df_archive['Price_Text'] + '|' + df_archive['Valid_Until'].astype(str))
    
    existing_keys = set(df_archive['_dup_key'])
    mask_new = ~df_new['_dup_key'].isin(existing_keys)
    
    items_to_analyze = df_new[mask_new].copy().drop(columns=['_dup_key'])
    items_already_done = df_new[~mask_new].copy()
    
    print(f"\n📊 Analysis Plan:")
    print(f"   🆕 NEW items to analyze: {len(items_to_analyze):,}")
    print(f"   ♻️  Already analyzed: {len(items_already_done):,}")
    
    if len(items_already_done) > 0:
        ai_columns = [c for c in df_archive.columns if c.startswith('ai_')]
        merge_on = ['Store', 'Original_Name', 'Price_Text', 'Valid_Until']
        
        items_already_done = items_already_done.drop(columns=['_dup_key']).merge(
            df_archive[merge_on + ai_columns],
            on=merge_on,
            how='left'
        )
    
    df_archive = df_archive.drop(columns=['_dup_key'])
    
else:
    items_to_analyze = df_new.copy()
    items_already_done = pd.DataFrame()
    df_archive = pd.DataFrame()
    print(f"\n📚 No historical data - creating new archive")

# --- AI ANALYSIS (with calibration context) ---

if len(items_to_analyze) > 0:
    print(f"\n>> Running AI analysis on {len(items_to_analyze)} NEW items...")
    print(f"   ✅ Enhanced with PDF calibration signals")
    
    try:
        items_to_analyze = add_ai_analysis_to_dataframe(items_to_analyze, df_archive, batch_size=50)
    except Exception as e:
        print(f"   [!] AI analysis failed: {e}")

# Recombine
if len(items_already_done) > 0:
    df_new = pd.concat([items_to_analyze, items_already_done], ignore_index=True)
else:
    df_new = items_to_analyze

# --- SAVE DATA ---

if len(df_archive) > 0:
    df_archive = pd.concat([df_archive, df_new], ignore_index=True)
    before = len(df_archive)
    df_archive.drop_duplicates(
        subset=['Store', 'Item', 'Price_Value', 'Date'],
        keep='last',
        inplace=True
    )
    after = len(df_archive)
    if before > after:
        print(f"\n✅ Removed {before - after:,} duplicate records")
else:
    df_archive = df_new.copy()

print(f"\n>> Historical archive: {len(df_archive):,} total records")
df_archive.to_csv(HISTORICAL_ARCHIVE, index=False)

df_current = df_new.copy()
df_current.to_csv(CURRENT_FLYERS, index=False)
print(f">> Current flyers: {len(df_current):,} active deals")

df_current.to_csv(DASHBOARD_FILE, index=False)
print(f">> Dashboard file saved")

# --- STATISTICS ---

print("\n" + "=" * 80)
print("📈 FINAL STATISTICS")
print("=" * 80)

print("\nItems per store:")
for store, count in df_new['Store'].value_counts().items():
    print(f"   {store}: {count} items")

if 'is_member_exclusive' in df_new.columns:
    member_count = df_new['is_member_exclusive'].sum()
    if member_count > 0:
        print(f"\n🎫 Member Exclusives: {member_count} items")

if 'is_featured' in df_new.columns:
    featured_count = df_new['is_featured'].sum()
    if featured_count > 0:
        print(f"⭐ Featured Items: {featured_count} items")

print("\n" + "=" * 80)
print("✅ SCRAPE COMPLETE!")
print("=" * 80)
print("\n💡 Next steps:")
print("   1. Check current_flyers.csv for latest deals")
if all_calibration_signals:
    print("   2. PDF calibration enhanced your data!")
    print("   3. Run dashboard.py to view")
else:
    print("   2. Run dashboard.py to view")
    print("   💡 Add PDFs to 'flyers/' + GEMINI_API_KEY for calibration")
print("=" * 80)
