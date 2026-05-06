"""
Enhanced Flipp Scraper with Multiple API Endpoints
V3.0 - Handles dead API links with fallbacks
"""
import requests
import json
import os
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import time
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🔧 API ENDPOINT CONFIGURATION
# ==========================================

# Multiple endpoint options (in order of preference)
API_ENDPOINTS = {
    'flyers': [
        "https://backflipp.wishabi.com/flipp/flyers",  # Original
        "https://backflipp.wishabi.com/flyers",         # Alternative path
        "https://flipp.com/api/flyers",                 # Direct
        "https://shopping.flipp.com/api/v3/flyers",     # Shopping API
    ],
    'items': [
        "https://backflipp.wishabi.com/flipp/flyers/{id}/items",  # Public API
        "https://backflipp.wishabi.com/flyers/{id}/items",        # Alt path
    ],
    'enterprise': "https://dam.flippenterprise.net/flyerkit/publication/{id}/products"
}

# ==========================================
# ⚙️ STORE CONFIGURATION  
# ==========================================

STORE_TOKENS = {
    "no frills": "1063f92aaf17b3dfa830cd70a685a52b",
    "real canadian": "a6e07e290f469d032d54a252f7582de2",
    "superstore": "a6e07e290f469d032d54a252f7582de2",
    "loblaw": "a6e07e290f469d032d54a252f7582de2",
    "co-op": "3e491961d82170af5a2044e66ea4a1a1",
    "calgary co-op": "3e491961d82170af5a2044e66ea4a1a1",
    "sobeys": "afbc75b4e335236182ac2fba092a0d4a",
    "safeway": "afbc75b4e335236182ac2fba092a0d4a", 
}

STORE_LIST = [
    "Real Canadian Superstore", "Sobeys", "Walmart", 
    "Calgary Co-op", "Safeway", "No Frills"
]

EXCLUDED_KEYWORDS = [
    "liquor", "pharmacy", "wine", "beer", "spirits", 
    "cannabis", "tobacco", "prescription", "optometry", "gift card"
]

POSTAL_CODE = os.getenv("POSTAL_CODE", "T2P 1J9")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://flipp.com",
    "Referer": "https://flipp.com/"
}

# ==========================================
# 🛠️ ENHANCED CORE FUNCTIONS
# ==========================================

def try_endpoints(endpoint_list, params=None, timeout=10):
    """
    Try multiple API endpoints until one works
    Returns (success, data, working_endpoint)
    """
    for endpoint in endpoint_list:
        try:
            res = requests.get(endpoint, params=params, headers=HEADERS, timeout=timeout)
            if res.status_code == 200:
                data = res.json()
                return True, data, endpoint
        except:
            continue
    return False, None, None

def get_active_flyers(postal_code):
    """Phase 1: Get flyer list with fallback endpoints"""
    print("📡 Trying to fetch flyer list...")
    
    params = {"locale": "en-ca", "postal_code": postal_code}
    success, data, working_endpoint = try_endpoints(API_ENDPOINTS['flyers'], params)
    
    if not success:
        print("❌ All flyer endpoints failed!")
        return []
    
    print(f"✅ Working endpoint: {working_endpoint}")
    
    flyers = []
    for f in data.get('flyers', []):
        name = f.get('merchant', '')
        matched_store = next((s for s in STORE_LIST if s.lower() in name.lower()), None)
        if matched_store:
            flyers.append({
                'id': f.get('id'),
                'store': matched_store,
                'merchant': name,
                'valid_to': f.get('valid_to')
            })
    
    return flyers

def download_flyer_items(flyer_id, store_name):
    """
    Phase 2: Enhanced Hybrid Engine with better fallbacks
    """
    clean_name = store_name.lower()
    items_list = []
    
    # --- PATH A: ENTERPRISE API (Priority) ---
    token = None
    for key, val in STORE_TOKENS.items():
        if key in clean_name:
            token = val
            break
    
    if token:
        url = API_ENDPOINTS['enterprise'].format(id=flyer_id)
        params = {'display_type': 'all', 'locale': 'en', 'access_token': token}
        
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json()
                
                for idx, item in enumerate(data):
                    name = item.get('name', '')
                    if any(x in name.lower() for x in EXCLUDED_KEYWORDS):
                        continue
                    
                    try:
                        price = float(item.get('current_price') or 0)
                    except ValueError:
                        continue
                    
                    if price <= 0:
                        continue

                    # Convert /kg prices
                    if "/kg" in name.lower() or "per kg" in name.lower():
                        price = round(price / 2.20462, 2)

                    items_list.append({
                        'id': item.get('id'),
                        'Item': name,
                        'Price_Value': price,
                        'Store': store_name,
                        'Valid_Until': item.get('valid_to'),
                        'Image': item.get('image_url'),
                        'Flyer_Order': idx
                    })
                
                if items_list:
                    print(f"   ✅ Enterprise API: {len(items_list)} items")
                    return items_list
            else:
                print(f"   ⚠️ Enterprise API returned status {res.status_code}")
        except Exception as e:
            print(f"   ⚠️ Enterprise API error: {str(e)[:50]}")

    # --- PATH B: PUBLIC API (Fallback with multiple endpoints) ---
    print(f"   🔄 Trying public API endpoints...")
    
    for endpoint_template in API_ENDPOINTS['items']:
        url = endpoint_template.format(id=flyer_id)
        
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json()
                
                # Try different possible keys for items
                items = data.get('items') or data.get('spread_items') or data.get('products') or []
                
                if not items:
                    continue
                
                for idx, item in enumerate(items):
                    if not item.get('current_price'):
                        continue
                    
                    name = item.get('name', '')
                    if any(x in name.lower() for x in EXCLUDED_KEYWORDS):
                        continue
                    
                    try:
                        price = float(item.get('current_price'))
                    except:
                        continue

                    if "/kg" in name.lower():
                        price = round(price / 2.20462, 2)

                    items_list.append({
                        'id': item.get('id'),
                        'Item': name,
                        'Price_Value': price,
                        'Store': store_name,
                        'Valid_Until': item.get('valid_to'),
                        'Image': item.get('thumbnail_url') or item.get('image_url'),
                        'Flyer_Order': idx
                    })
                
                if items_list:
                    print(f"   ✅ Public API: {len(items_list)} items from {url}")
                    return items_list
                    
        except Exception as e:
            continue
    
    print(f"   ❌ All endpoints failed for {store_name}")
    return []

def save_safely(df, filename):
    """Atomic write to prevent corruption"""
    temp_file = f"{filename}.tmp"
    try:
        df.to_csv(temp_file, index=False, encoding='utf-8-sig')
        if os.path.exists(filename):
            os.remove(filename)
        os.rename(temp_file, filename)
        print(f"✅ Saved {len(df)} records to '{filename}'")
    except Exception as e:
        print(f"❌ Failed to save '{filename}': {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

# ==========================================
# 🚀 MAIN EXECUTION
# ==========================================

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"🛒 FLIPP SCRAPER V3.0 - Enhanced Error Handling")
    print(f"{'='*70}\n")
    
    # Phase 1: Find Flyers
    flyers = get_active_flyers(POSTAL_CODE)
    
    if not flyers:
        print("\n❌ CRITICAL: Could not fetch flyer list")
        print("\nPossible issues:")
        print("  1. All API endpoints are down")
        print("  2. Network/firewall blocking requests")
        print("  3. Postal code not recognized")
        print("\nTroubleshooting:")
        print("  - Run test_api_endpoints.py to diagnose")
        print("  - Try different postal code")
        print("  - Check if flipp.com is accessible")
        exit(1)
    
    print(f"✅ Found {len(flyers)} active flyers\n")
    
    # Phase 2: Scrape
    all_deals = []
    print("⬇️ Downloading deals...\n")
    
    for i, f in enumerate(flyers):
        print(f"[{i+1}/{len(flyers)}] {f['store']}...")
        items = download_flyer_items(f['id'], f['store'])
        
        if items:
            all_deals.extend(items)
        
        time.sleep(1)
    
    # Phase 3: Save
    if all_deals:
        print(f"\n✅ Successfully scraped {len(all_deals)} deals")
        
        df = pd.DataFrame(all_deals)
        df['Date'] = datetime.now().strftime("%Y-%m-%d")
        
        # Save current
        save_safely(df, "current_flyers.csv")
        
        # Update history
        history_file = "historical_archive.csv"
        if os.path.exists(history_file):
            try:
                history = pd.read_csv(history_file)
                combined = pd.concat([history, df])
                combined = combined.drop_duplicates(
                    subset=['Store', 'Item', 'Date'], 
                    keep='last'
                )
                save_safely(combined, history_file)
                print(f"📚 History updated: {len(combined)} total records")
            except Exception as e:
                print(f"⚠️ Error updating history: {e}")
        else:
            save_safely(df, history_file)
            print("📚 Created new historical archive")
        
        print(f"\n{'='*70}")
        print("✅ SCRAPE COMPLETE!")
        print(f"{'='*70}")
    else:
        print("\n❌ NO ITEMS RETRIEVED")
        print("\nDiagnosis:")
        print("  - Flyers were found but item endpoints all failed")
        print("  - This likely means the item API endpoints are dead")
        print("\nNext steps:")
        print("  1. Run: python test_api_endpoints.py")
        print("  2. Check if enterprise tokens are still valid")
        print("  3. Consider alternative scraping (Selenium, Playwright)")
