"""
Flipp API Endpoint Diagnostic Tool
Tests all endpoints to identify which are dead
"""
import requests
import json
from datetime import datetime

# Store tokens from your config
STORE_TOKENS = {
    "no frills": "1063f92aaf17b3dfa830cd70a685a52b",
    "superstore": "a6e07e290f469d032d54a252f7582de2",
    "co-op": "3e491961d82170af5a2044e66ea4a1a1",
    "sobeys": "afbc75b4e335236182ac2fba092a0d4a",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://flipp.com",
    "Referer": "https://flipp.com/"
}

POSTAL_CODE = "T2P 1J9"

def test_endpoint(name, url, params=None, method="GET"):
    """Test a single endpoint"""
    print(f"\n{'='*70}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    if params:
        print(f"Params: {params}")
    
    try:
        if method == "GET":
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        else:
            response = requests.post(url, json=params, headers=HEADERS, timeout=15)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"✅ SUCCESS - Response is valid JSON")
                
                # Show structure
                if isinstance(data, dict):
                    print(f"Keys: {list(data.keys())[:10]}")
                    if 'flyers' in data:
                        print(f"Flyers found: {len(data['flyers'])}")
                    if 'items' in data:
                        print(f"Items found: {len(data['items'])}")
                elif isinstance(data, list):
                    print(f"List with {len(data)} items")
                    if data:
                        print(f"First item keys: {list(data[0].keys())[:10]}")
                
                return True, data
            except:
                print(f"⚠️  Status 200 but response is not JSON")
                print(f"Response preview: {response.text[:200]}")
                return False, None
        else:
            print(f"❌ FAILED - Status {response.status_code}")
            print(f"Response preview: {response.text[:200]}")
            return False, None
            
    except requests.exceptions.Timeout:
        print(f"❌ TIMEOUT - Request took too long")
        return False, None
    except requests.exceptions.ConnectionError as e:
        print(f"❌ CONNECTION ERROR - {str(e)[:100]}")
        return False, None
    except Exception as e:
        print(f"❌ ERROR - {str(e)[:100]}")
        return False, None

print(f"\n{'#'*70}")
print(f"# FLIPP API DIAGNOSTIC REPORT")
print(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'#'*70}\n")

# Test 1: Old Backflipp API (your current code)
success1, data1 = test_endpoint(
    "Old Backflipp API - Get Flyers",
    "https://backflipp.wishabi.com/flipp/flyers",
    params={"locale": "en-ca", "postal_code": POSTAL_CODE}
)

# Test 2: Try without 'flipp' in path
success2, data2 = test_endpoint(
    "Wishabi API (alt path) - Get Flyers",
    "https://backflipp.wishabi.com/flyers",
    params={"locale": "en-ca", "postal_code": POSTAL_CODE}
)

# Test 3: Direct Flipp.com API
success3, data3 = test_endpoint(
    "Flipp.com Direct API",
    "https://flipp.com/api/flyers",
    params={"postal_code": POSTAL_CODE}
)

# Test 4: Flipp shopping API
success4, data4 = test_endpoint(
    "Flipp Shopping API",
    "https://shopping.flipp.com/api/v3/flyers",
    params={"postal_code": POSTAL_CODE}
)

# Test 5: If we got flyers, test getting items
flyer_id = None
if success1 and data1 and 'flyers' in data1 and data1['flyers']:
    flyer_id = data1['flyers'][0]['id']
    print(f"\n\n{'='*70}")
    print(f"Found flyer ID: {flyer_id}")
    print(f"Testing item endpoints with this ID...")
    
    # Test old public API
    test_endpoint(
        "Old Public API - Get Items",
        f"https://backflipp.wishabi.com/flipp/flyers/{flyer_id}/items"
    )
    
    # Test enterprise API (with Co-op token)
    test_endpoint(
        "Enterprise API - Get Products",
        f"https://dam.flippenterprise.net/flyerkit/publication/{flyer_id}/products",
        params={
            'display_type': 'all',
            'locale': 'en',
            'access_token': STORE_TOKENS['co-op']
        }
    )

# Summary
print(f"\n\n{'='*70}")
print(f"SUMMARY")
print(f"{'='*70}")
results = [
    ("Old Backflipp API", success1),
    ("Wishabi Alt Path", success2),
    ("Flipp.com Direct", success3),
    ("Shopping API", success4),
]

for name, success in results:
    status = "✅ WORKING" if success else "❌ DEAD"
    print(f"{name:30} {status}")

print(f"\n{'='*70}")
print(f"RECOMMENDATION:")
print(f"{'='*70}")

if any([s for _, s in results]):
    print("Some endpoints are working. Update your script to use the working ones.")
else:
    print("⚠️  ALL ENDPOINTS FAILED")
    print("Possible causes:")
    print("  1. Network restrictions in this environment")
    print("  2. Flipp changed their API completely")
    print("  3. Need to run this test from your local machine")
    print("\nNext steps:")
    print("  - Run this script on your local machine where the scraper works")
    print("  - Check if Flipp has API documentation")
    print("  - Consider alternative scraping methods (Selenium, etc.)")
