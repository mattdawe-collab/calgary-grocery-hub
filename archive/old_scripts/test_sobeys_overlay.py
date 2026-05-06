"""
Test Scraper - Sobeys Only
Quick test to check if Flipp API returns item coordinates for overlay feature
"""

import requests
import json
from datetime import datetime

# Configuration
POSTAL_CODE = "T3M1M9"
BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

def get_active_flyers(postal_code):
    """Get active flyers"""
    url = f"{BASE_URL}/flyers"
    params = {'postal_code': postal_code, 'locale': 'en-ca'}
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.json().get('flyers', [])
    except Exception as e:
        print(f"Error: {e}")
    
    return []

def get_flyer_full_data(flyer_id):
    """Get complete flyer data including items and images"""
    url = f"{BASE_URL}/flyers/{flyer_id}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def analyze_flyer_structure(flyer_data, store_name):
    """Analyze what data the flyer API returns"""
    
    print("\n" + "=" * 70)
    print(f"📊 FLYER STRUCTURE ANALYSIS - {store_name}")
    print("=" * 70)
    
    # Top-level keys
    print("\n🔑 Top-level keys in flyer data:")
    for key in flyer_data.keys():
        print(f"   • {key}")
    
    # Items analysis
    items = flyer_data.get('items', []) or flyer_data.get('flyer_items', [])
    
    if items:
        print(f"\n📦 Found {len(items)} items")
        
        # Analyze first item structure
        print("\n🔍 Sample item structure (first item):")
        sample_item = items[0]
        
        for key, value in sample_item.items():
            value_type = type(value).__name__
            
            # Truncate long values
            if isinstance(value, str) and len(value) > 50:
                value_display = f"{value[:47]}..."
            elif isinstance(value, dict):
                value_display = f"{{dict with {len(value)} keys}}"
            elif isinstance(value, list):
                value_display = f"[list with {len(value)} items]"
            else:
                value_display = str(value)
            
            print(f"   • {key}: {value_display} ({value_type})")
        
        # Check for position data
        print("\n📍 POSITION DATA CHECK:")
        position_fields = ['x', 'y', 'width', 'height', 'position', 'coordinates', 'bounds']
        found_positions = []
        
        for field in position_fields:
            if field in sample_item:
                found_positions.append(field)
                print(f"   ✅ {field}: {sample_item[field]}")
        
        if not found_positions:
            print("   ❌ No position coordinates found in items")
            print("   💡 May need to check 'flyer_images' or use OCR")
    else:
        print("\n❌ No items found in flyer data")
    
    # Images analysis
    images = flyer_data.get('flyer_images', []) or flyer_data.get('images', [])
    
    if images:
        print(f"\n🖼️  Found {len(images)} flyer images/pages")
        
        sample_image = images[0]
        print("\n🔍 Sample image structure:")
        for key, value in sample_image.items():
            value_type = type(value).__name__
            
            if isinstance(value, str) and len(value) > 50:
                value_display = f"{value[:47]}..."
            else:
                value_display = str(value)
            
            print(f"   • {key}: {value_display} ({value_type})")
    else:
        print("\n❌ No flyer images found")
    
    # Check for spread items (items organized by page)
    spread_items = flyer_data.get('spread_items', [])
    if spread_items:
        print(f"\n📄 Found {len(spread_items)} spread items (items by page)")
        
        sample_spread = spread_items[0]
        print("\n🔍 Sample spread item structure:")
        for key, value in sample_spread.items():
            value_type = type(value).__name__
            
            if isinstance(value, str) and len(value) > 50:
                value_display = f"{value[:47]}..."
            elif isinstance(value, dict):
                value_display = f"{{dict with {len(value)} keys}}"
            elif isinstance(value, list):
                value_display = f"[list with {len(value)} items]"
            else:
                value_display = str(value)
            
            print(f"   • {key}: {value_display} ({value_type})")

def main():
    """Main test function"""
    
    print("=" * 70)
    print("🧪 SOBEYS FLYER OVERLAY TEST")
    print("=" * 70)
    print(f"\nSearching for Sobeys flyers near {POSTAL_CODE}...")
    
    # Get flyers
    flyers = get_active_flyers(POSTAL_CODE)
    
    if not flyers:
        print("\n❌ No flyers found!")
        return
    
    # Find Sobeys flyer
    sobeys_flyer = None
    for flyer in flyers:
        merchant = flyer.get('merchant', '').lower()
        if 'sobeys' in merchant or 'safeway' in merchant:
            sobeys_flyer = flyer
            print(f"\n✅ Found: {flyer['merchant']}")
            print(f"   ID: {flyer['id']}")
            print(f"   Name: {flyer.get('name', 'N/A')}")
            print(f"   Valid: {flyer.get('valid_from', 'N/A')} to {flyer.get('valid_to', 'N/A')}")
            break
    
    if not sobeys_flyer:
        print("\n❌ No Sobeys/Safeway flyer found!")
        print("\nAvailable stores:")
        for f in flyers[:10]:
            print(f"   • {f['merchant']}")
        return
    
    # Get full flyer data
    print(f"\n📥 Fetching full flyer data for ID {sobeys_flyer['id']}...")
    
    flyer_data = get_flyer_full_data(sobeys_flyer['id'])
    
    if not flyer_data:
        print("\n❌ Could not fetch flyer data!")
        return
    
    # Analyze structure
    analyze_flyer_structure(flyer_data, sobeys_flyer['merchant'])
    
    # Save raw data for inspection
    output_file = f"sobeys_flyer_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_file, 'w') as f:
        json.dump(flyer_data, f, indent=2)
    
    print("\n" + "=" * 70)
    print(f"✅ Raw flyer data saved to: {output_file}")
    print("=" * 70)
    
    # Summary
    print("\n📋 SUMMARY:")
    
    items = flyer_data.get('items', []) or flyer_data.get('flyer_items', [])
    images = flyer_data.get('flyer_images', []) or flyer_data.get('images', [])
    
    print(f"   • Items found: {len(items)}")
    print(f"   • Images found: {len(images)}")
    
    # Check for position data
    if items:
        has_coords = any(key in items[0] for key in ['x', 'y', 'position', 'coordinates'])
        
        if has_coords:
            print("\n   ✅ OVERLAY POSSIBLE: Item coordinates found!")
            print("   💡 We can overlay AI badges directly on flyer images!")
        else:
            print("\n   ⚠️  NO COORDINATES: Will need OCR or manual mapping")
            print("   💡 Alternative: Create AI badges separate from flyer layout")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
