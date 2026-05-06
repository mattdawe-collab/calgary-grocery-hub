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

# PDF Validation imports
import json
import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
import io
import google.generativeai as genai

# --- 1. CONFIGURATION & SECRETS ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Files
HISTORICAL_ARCHIVE = 'historical_archive.csv'  # All-time archive with AI columns
CURRENT_FLYERS = 'current_flyers.csv'  # Latest flyer per store
DASHBOARD_FILE = 'clean_grocery_data.csv'  # Backwards compatibility

# Scraper Settings
POSTAL_CODE = "T3M1M9"
STORES = [
    "Real Canadian Superstore", "Save-On-Foods", "Calgary Co-op",
    "Sobeys", "Safeway", "No Frills"
]

# EXCLUSION FILTERS - Skip these merchant names entirely
EXCLUDED_MERCHANTS = [
    "liquor",      # Sobeys & Safeway Liquor
    "pharmacy",    # Pharmacy-only flyers
    "wine",
    "beer",
    "spirits",
    "lcbo",
    "liquor store"
]

BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

# --- 1.5 PDF VALIDATION FUNCTIONS ---

def pdf_verification_enabled():
    """Check if PDF verification should run."""
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

def pdf_to_images(pdf_path, dpi=150):
    """Convert PDF pages to images."""
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

def extract_pdf_ground_truth(images, store_name):
    """Extract complete item list from PDF using Gemini 3.0 Flash.
    Processes ONE PAGE AT A TIME for maximum quality and reliability.
    """
    
    all_items = []
    
    print(f"      📄 Processing {len(images)} pages individually for maximum quality...")
    
    for page_num, img in enumerate(images, 1):
        try:
            model = genai.GenerativeModel(
                'gemini-3-flash-preview',
                system_instruction="""You are a highly thorough grocery deal extractor. Your goal is 100% RECALL.
Extract every product that has an associated price, discount, or multi-buy offer.

Output Format: ProductName | Price/Discount | MEMBER or REGULAR

CRITICAL INSTRUCTIONS:
- PRICE BUBBLES: Look for large numbers in circles; these are prices.
- WEIGHT UNITS: Check for /lb, /kg, or /100g near the price. Include them in the Price column.
- MULTI-BUYS: Capture "2 for $7" or "3/$10" exactly as written.
- DISCOUNTS: If no price is listed but a % exists (e.g., 57% OFF), extract it as the price.
- MULTI-LINE NAMES: Group descriptions (e.g., "Grain Fed", "Family Pack") into the ProductName.
- SMALL TEXT: Don't skip items with small fonts - these are often important deals.
- NO SKIPPING: If a line is messy, extract your best guess rather than omitting it.

MEMBER INDICATORS: Mark as "MEMBER" if you see:
- "Member Price", "Club Price", "MyOffers", or membership badges
Otherwise mark as "REGULAR"

Extract aggressively. Your recall target is 100%."""
            )
            
            # Ultra-simple prompt
            prompt = "List every product with a price on this page:"
            
            # Process single image with HIGH QUALITY settings
            buffered = io.BytesIO()
            img.save(buffered, format="PNG", optimize=True, quality=95)
            
            # GEMINI 3 FLASH OPTIMIZED CONFIGURATION
            # Note: thinking_level may require SDK update, so we use compatible params
            gen_config = {
                "temperature": 1.0,           # Default for reasoning models (allows internal reasoning)
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 16000    # High limit for reasoning + all items
            }
            
            response = model.generate_content(
                [prompt, {'mime_type': 'image/png', 'data': buffered.getvalue()}],
                generation_config=gen_config
            )
            
            response_text = response.text.strip()
            
            # DEBUG: Show what Gemini returned
            lines_returned = len([l for l in response_text.split('\n') if l.strip()])
            chars_returned = len(response_text)
            print(f"         Page {page_num}: Gemini returned {lines_returned} lines ({chars_returned} chars)")
            
            # Show first few lines and last few lines to check for truncation
            response_lines = [l.strip() for l in response_text.split('\n') if l.strip()]
            if response_lines:
                print(f"            First: {response_lines[0][:80]}")
                if len(response_lines) > 1:
                    print(f"            Last:  {response_lines[-1][:80]}")
                
                # Check if last line looks truncated (no closing pipe or incomplete)
                last_line = response_lines[-1]
                if last_line.count('|') < 2:
                    print(f"            ⚠️  WARNING: Last line may be truncated!")
            
            # Parse this page's items
            page_items = 0
            for line in response_text.split('\n'):
                line = line.strip()
                
                # Skip empty lines, headers, and non-data lines
                if not line or '|' not in line:
                    continue
                
                # Skip header line if Gemini included it
                if 'ProductName' in line or 'Price/Discount' in line or 'MEMBER or REGULAR' in line:
                    continue
                
                try:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) < 3:
                        continue
                    
                    name = parts[0]
                    price_text = parts[1]
                    member_status = parts[2].upper()
                    
                    # Skip if no actual content
                    if not name or not price_text:
                        continue
                    
                    # Parse price value
                    price_value = 0.0
                    try:
                        price_clean = price_text.replace('$', '').replace(',', '').strip()
                        
                        # Handle multi-buy: "2/$5" → 2.50 per item
                        if '/' in price_clean:
                            parts_price = price_clean.split('/')
                            if len(parts_price) == 2:
                                left = parts_price[0].strip()
                                right = parts_price[1].strip()
                                
                                # Check if left is quantity (2/$5)
                                if left.replace('.','').isdigit():
                                    qty = float(left)
                                    total = float(right) if right.replace('.','').replace('lb','').replace('kg','').isdigit() else 0
                                    if qty > 0:
                                        price_value = total / qty
                                else:
                                    # It's per-weight: $4/lb
                                    price_value = float(left) if left.replace('.','').isdigit() else 0
                        else:
                            # Regular price - extract first number
                            import re
                            numbers = re.findall(r'\d+\.?\d*', price_clean)
                            if numbers:
                                price_value = float(numbers[0])
                    except:
                        price_value = 0.0
                    
                    # Determine position based on rough thirds
                    if page_num == 1:
                        position = 'top'
                    elif page_num <= len(images) // 2:
                        position = 'middle'  
                    else:
                        position = 'bottom'
                    
                    # Check for member pricing
                    is_member = 'MEMBER' in member_status
                    member_indicator = None
                    if is_member:
                        # Try to identify specific indicator
                        if 'club' in member_status.lower():
                            member_indicator = 'Club Price'
                        elif 'myoffer' in member_status.lower():
                            member_indicator = 'MyOffers'
                        else:
                            member_indicator = 'Member Price'
                    
                    all_items.append({
                        'name': name,
                        'price_text': price_text,
                        'price_value': price_value,
                        'page': page_num,
                        'position': position,
                        'is_member_exclusive': is_member,
                        'member_indicator': member_indicator
                    })
                    page_items += 1
                    
                except Exception as e:
                    # Skip malformed lines silently
                    continue
            
            if page_items > 0:
                print(f"            ✅ Parsed {page_items} items successfully")
            else:
                print(f"            ⚠️  No items parsed (check format above)")
            
            # FALLBACK: If very few items found, try again with more aggressive prompt
            if page_items < 5 and page_num <= 3:  # Only retry early pages
                print(f"            🔄 Low recall detected - retrying with aggressive extraction...")
                
                aggressive_prompt = """I see very few items were extracted. Look MORE CAREFULLY at:
- Red/yellow price circles and bubbles
- Bold text with prices
- Small text in corners
- Product grids
- ALL visible prices

List EVERY product with a price. Don't be conservative - extract everything you see."""
                
                try:
                    retry_response = model.generate_content(
                        [aggressive_prompt, {'mime_type': 'image/png', 'data': buffered.getvalue()}],
                        generation_config=gen_config
                    )
                    
                    retry_text = retry_response.text.strip()
                    retry_items = 0
                    
                    for line in retry_text.split('\n'):
                        line = line.strip()
                        if not line or '|' not in line:
                            continue
                        if 'ProductName' in line or 'Price/Discount' in line:
                            continue
                        
                        try:
                            parts = [p.strip() for p in line.split('|')]
                            if len(parts) >= 3 and parts[0] and parts[1]:
                                # Only add if not already captured
                                name_lower = parts[0].lower()
                                already_have = any(
                                    item['name'].lower() == name_lower 
                                    for item in all_items 
                                    if item['page'] == page_num
                                )
                                if not already_have:
                                    # Parse and add (using same logic as before)
                                    price_value = 0.0
                                    try:
                                        import re
                                        nums = re.findall(r'\d+\.?\d*', parts[1])
                                        if nums:
                                            price_value = float(nums[0])
                                    except:
                                        pass
                                    
                                    all_items.append({
                                        'name': parts[0],
                                        'price_text': parts[1],
                                        'price_value': price_value,
                                        'page': page_num,
                                        'position': 'top' if page_num == 1 else 'middle',
                                        'is_member_exclusive': 'MEMBER' in parts[2].upper(),
                                        'member_indicator': 'Member Price' if 'MEMBER' in parts[2].upper() else None
                                    })
                                    retry_items += 1
                        except:
                            continue
                    
                    if retry_items > 0:
                        print(f"            ✅ Retry found {retry_items} additional items!")
                        page_items += retry_items
                except Exception as e:
                    print(f"            ⚠️  Retry failed: {str(e)[:50]}")
            
            # Brief pause between pages to avoid rate limits
            if page_num < len(images):
                time.sleep(0.5)
                
        except Exception as e:
            print(f"         Page {page_num}: ❌ Error - {str(e)[:60]}")
            continue
    
    if all_items:
        print(f"      ✅ Total extracted: {len(all_items)} items across {len(images)} pages")
        return {
            'store': store_name,
            'items': all_items
        }
    else:
        print(f"      ⚠️  No items extracted from any pages")
        return None

def match_api_to_pdf(api_items, pdf_items):
    """Match API items to PDF ground truth using fuzzy matching."""
    
    enhanced_items = []
    
    for api_item in api_items:
        api_name = api_item.get('Item', '').lower()
        api_price = float(api_item.get('Price_Value', 0))
        
        # Find best PDF match
        best_match = None
        best_score = 0
        
        for pdf_item in pdf_items:
            pdf_name = pdf_item.get('name', '').lower()
            pdf_price = float(pdf_item.get('price_value', 0))
            
            # Name similarity score
            name_score = 0
            if api_name in pdf_name or pdf_name in api_name:
                name_score = 0.8
            else:
                api_words = set(w for w in api_name.split() if len(w) > 3)
                pdf_words = set(w for w in pdf_name.split() if len(w) > 3)
                if api_words and pdf_words:
                    overlap = len(api_words & pdf_words) / len(api_words | pdf_words)
                    name_score = overlap * 0.6
            
            # Price similarity bonus
            if api_price > 0 and pdf_price > 0:
                price_diff = abs(api_price - pdf_price) / api_price
                if price_diff < 0.1:
                    name_score += 0.2
            
            if name_score > best_score:
                best_score = name_score
                best_match = pdf_item
        
        # Enhance with PDF data
        enhanced = api_item.copy()
        
        if best_match and best_score > 0.5:
            enhanced['pdf_matched'] = True
            enhanced['pdf_match_confidence'] = round(best_score, 2)
            enhanced['pdf_price'] = best_match.get('price_value')
            enhanced['price_difference'] = api_price - best_match.get('price_value', 0)
            enhanced['is_member_exclusive'] = best_match.get('is_member_exclusive', False)
            enhanced['member_indicator'] = best_match.get('member_indicator')
            enhanced['pdf_page'] = best_match.get('page')
            enhanced['pdf_position'] = best_match.get('position')
            
            # Validation status
            if abs(enhanced['price_difference']) < 0.10:
                enhanced['validation_status'] = 'verified'
            else:
                enhanced['validation_status'] = 'price_mismatch'
        else:
            enhanced['pdf_matched'] = False
            enhanced['validation_status'] = 'not_in_pdf'
            enhanced['is_member_exclusive'] = False
        
        enhanced_items.append(enhanced)
    
    return enhanced_items

def verify_with_pdfs(df_current):
    """Verify and enhance data with PDF flyers."""
    
    print("\n" + "=" * 80)
    print("📄 PDF VALIDATION & VERIFICATION")
    print("   Powered by Gemini 3.0 Flash")
    print("=" * 80)
    
    pdf_folder = Path("flyers")
    if not pdf_folder.exists():
        print("\n💡 No 'flyers' folder - continuing with API data only")
        return df_current, None
    
    pdfs = list(pdf_folder.glob("*.pdf"))
    if not pdfs:
        print("\n💡 No PDFs found - continuing with API data only")
        return df_current, None
    
    # Match PDFs to stores
    store_pdfs = {}
    for pdf in pdfs:
        store = extract_store_from_filename(pdf.name)
        if store and store in df_current['Store'].values:
            if store not in store_pdfs or pdf.stat().st_mtime > store_pdfs[store].stat().st_mtime:
                store_pdfs[store] = pdf
    
    if not store_pdfs:
        print("\n⚠️  PDFs found but couldn't match to stores")
        print("   Tip: Name PDFs like 'Sobeys Dec 31-Jan 6.pdf'")
        return df_current, None
    
    print(f"\n✅ Found {len(store_pdfs)} matching PDFs:")
    for store, pdf in store_pdfs.items():
        print(f"   {store}: {pdf.name}")
    
    if not os.getenv('GEMINI_API_KEY'):
        print("\n⚠️  GEMINI_API_KEY not found - continuing with API data only")
        print("   Add GEMINI_API_KEY to .env to enable PDF validation")
        return df_current, None
    
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    
    # Extract from each PDF
    all_pdf_data = {}
    total_cost = 0
    
    for store_idx, (store, pdf_path) in enumerate(store_pdfs.items()):
        print(f"\n🏪 {store}: {pdf_path.name}")
        
        try:
            print(f"   🔄 Converting to images...")
            images = pdf_to_images(pdf_path, dpi=300)  # Increased from 150 for better OCR
            print(f"      ✅ {len(images)} pages")
            
            cost = 0.015 * len(images)
            total_cost += cost
            print(f"   🤖 Extracting with Gemini 3 Flash (${cost:.3f})...")
            print(f"      Processing page-by-page for maximum quality...")
            
            # Always process page by page
            pdf_result = extract_pdf_ground_truth(images, store)
            
            if pdf_result and 'items' in pdf_result:
                pdf_items = pdf_result['items']
                all_pdf_data[store] = pdf_items
                
                member_count = sum(1 for item in pdf_items if item.get('is_member_exclusive'))
                print(f"      ✅ Total: {len(pdf_items)} items extracted")
                if member_count > 0:
                    print(f"         🎫 {member_count} member exclusives detected")
            else:
                print(f"      ⚠️  Extraction failed - no items found")
                
        except Exception as e:
            print(f"      ❌ Error: {str(e)[:80]}...")
            continue
        
        if store_idx < len(store_pdfs) - 1:
            print(f"      ⏳ Waiting 2 seconds before next store...")
            time.sleep(2)
    
    if not all_pdf_data:
        print("\n⚠️  No PDF data extracted")
        return df_current, None
    
    # Match API to PDF
    print(f"\n" + "=" * 80)
    print(f"🔗 MATCHING API TO PDF")
    print("=" * 80)
    
    enhanced_rows = []
    validation_stats = {
        'verified': 0,
        'price_mismatch': 0,
        'not_in_pdf': 0,
        'member_exclusive': 0
    }
    
    for store in df_current['Store'].unique():
        store_rows = df_current[df_current['Store'] == store].to_dict('records')
        
        if store in all_pdf_data:
            pdf_items = all_pdf_data[store]
            print(f"\n   {store}: Matching {len(store_rows)} API → {len(pdf_items)} PDF...")
            
            enhanced = match_api_to_pdf(store_rows, pdf_items)
            
            verified = sum(1 for item in enhanced if item.get('validation_status') == 'verified')
            mismatches = sum(1 for item in enhanced if item.get('validation_status') == 'price_mismatch')
            not_in_pdf = sum(1 for item in enhanced if item.get('validation_status') == 'not_in_pdf')
            members = sum(1 for item in enhanced if item.get('is_member_exclusive'))
            
            print(f"      ✅ {verified} verified | ⚠️  {mismatches} mismatches | 📭 {not_in_pdf} not in PDF | 🎫 {members} members")
            
            validation_stats['verified'] += verified
            validation_stats['price_mismatch'] += mismatches
            validation_stats['not_in_pdf'] += not_in_pdf
            validation_stats['member_exclusive'] += members
            
            enhanced_rows.extend(enhanced)
        else:
            enhanced_rows.extend(store_rows)
    
    df_enhanced = pd.DataFrame(enhanced_rows)
    
    # Save member exclusives report
    member_items = []
    for store, pdf_items in all_pdf_data.items():
        for item in pdf_items:
            if item.get('is_member_exclusive'):
                member_items.append({
                    'Store': store,
                    'Item': item.get('name'),
                    'Price': item.get('price_text'),
                    'Indicator': item.get('member_indicator'),
                    'Page': item.get('page')
                })
    
    if member_items:
        pd.DataFrame(member_items).to_csv('member_exclusive_items.csv', index=False)
    
    print(f"\n" + "=" * 80)
    print(f"📊 PDF VALIDATION COMPLETE")
    print("=" * 80)
    print(f"\n💰 Total cost: ${total_cost:.3f}")
    print(f"\n✅ Validation Results:")
    print(f"   Verified: {validation_stats['verified']}")
    print(f"   Price mismatches: {validation_stats['price_mismatch']}")
    print(f"   Not in PDF: {validation_stats['not_in_pdf']}")
    print(f"   Member exclusives: {validation_stats['member_exclusive']}")
    
    if member_items:
        print(f"\n🎫 Member exclusives saved to: member_exclusive_items.csv")
    
    # Create PDF context for AI
    pdf_context = {}
    for store, pdf_items in all_pdf_data.items():
        member_items_store = [item for item in pdf_items if item.get('is_member_exclusive')]
        if member_items_store:
            pdf_context[store] = f"""
PDF CONTEXT FOR {store}:
Total items in PDF: {len(pdf_items)}
Member-exclusive items: {len(member_items_store)}

Member Items (first 10):
{json.dumps([{'name': i.get('name'), 'price': i.get('price_text'), 'indicator': i.get('member_indicator')} for i in member_items_store[:10]], indent=2)}

IMPORTANT: Member items require store membership for listed price. When analyzing deals, note if membership is required."""
    
    return df_enhanced, pdf_context

# --- 2. CLEANER CONFIGURATION (Category Mapping) ---
CATEGORY_MAP = {
    # Meat & Protein
    "Meat": "Meat & Protein", "Meat & Seafood": "Meat & Protein", 
    "Deli": "Meat & Protein", "Prepared Meals": "Meat & Protein", 
    "Seafood": "Meat & Protein", "Fish": "Meat & Protein",
    # Dairy & Fridge
    "Dairy": "Dairy & Fridge", "Dairy & Eggs": "Dairy & Fridge", 
    "Yogurt": "Dairy & Fridge", "Cheese": "Dairy & Fridge",
    "Milk": "Dairy & Fridge", "Butter": "Dairy & Fridge", "Frozen": "Dairy & Fridge", 
    # Produce
    "Produce": "Produce", "Fruit": "Produce", "Vegetables": "Produce",
    # Pantry
    "Pantry": "Pantry & Household", "Baking": "Pantry & Household", 
    "Baking Goods": "Pantry & Household", "Baked Goods": "Pantry & Household",
    "Meal Kits": "Pantry & Household", "Nuts & Seeds": "Pantry & Household",
    "Canned": "Pantry & Household", "Condiments": "Pantry & Household",
    # Snacks
    "Snacks": "Snacks & Treats", "Candy": "Snacks & Treats", 
    "Sweets": "Snacks & Treats", "Confectionery": "Snacks & Treats", 
    "Desserts": "Snacks & Treats", "Beverages": "Snacks & Treats",
    "Chips": "Snacks & Treats", "Cookies": "Snacks & Treats",
    # Health & Home
    "Health": "Health & Home", "Personal Care": "Health & Home", 
    "Pets": "Health & Home", "Baby": "Health & Home", 
    "Cleaning": "Health & Home", "Paper": "Health & Home"
}

# --- 3. HELPER FUNCTIONS ---
def is_excluded_merchant(merchant_name):
    """
    Check if merchant should be excluded (e.g., liquor stores)
    Returns True if should be SKIPPED
    """
    if not merchant_name:
        return False
    
    merchant_lower = merchant_name.lower()
    
    for excluded in EXCLUDED_MERCHANTS:
        if excluded in merchant_lower:
            print(f"   ⚠️  SKIPPING: {merchant_name} (contains '{excluded}')")
            return True
    
    return False

def get_active_flyers(postal_code):
    url = f"{BASE_URL}/flyers"
    params = {'postal_code': postal_code, 'locale': 'en-ca'}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        return response.json().get('flyers', [])
    except:
        return []

def get_flyer_items(flyer_id):
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
    """
    Enhanced price cleaning that handles:
    - Multi-buy deals (2 for $5)
    - Per-weight pricing (/lb, /kg, /100g)
    - Regular prices
    Returns: (raw_price_text, unit_price, normalized_per_kg_text)
    """
    keys = ['price', 'current_price', 'price_text', 'sale_price', 'original_price']
    raw_price = next((item_dict[k] for k in keys if item_dict.get(k)), None)
    
    if not raw_price: 
        return None, None, None
    
    try:
        clean = str(raw_price).replace('$', '').replace('Â¢', '').lower().strip()
        
        # Check for per-weight pricing (e.g., "$5.99/lb", "$11.99/kg", "$3.99/100g")
        per_weight = re.search(r'(\d+(?:\.\d+)?)\s*(?:/|per)\s*(lb|lbs|kg|100g|g)', clean)
        if per_weight:
            price = float(per_weight.group(1))
            unit = per_weight.group(2).replace('lbs', 'lb')
            
            # Normalize to per kg for comparison
            if unit == 'lb':
                normalized_price = price * 2.20462  # Convert $/lb to $/kg
            elif unit == '100g':
                normalized_price = price * 10  # Convert $/100g to $/kg
            elif unit == 'g':
                normalized_price = price * 1000  # Convert $/g to $/kg
            else:  # already kg
                normalized_price = price
            
            return raw_price, price, f"${normalized_price:.2f}/kg"
        
        # Check for multi-buy deals (e.g., "2 for $5", "3/$10")
        multibuy = re.search(r'(\d+)\s*(?:/|for)\s*\$?(\d+(?:\.\d+)?)', clean)
        if multibuy:
            qty = float(multibuy.group(1))
            total_price = float(multibuy.group(2))
            if qty > 0: 
                unit_price = total_price / qty
                return raw_price, unit_price, None
        
        # Regular price - just extract the number
        matches = re.findall(r"[-+]?(?:\d*\.\d+|\d+)", clean)
        if matches: 
            return raw_price, float(matches[0]), None
        
        return raw_price, None, None
        
    except Exception as e:
        print(f"   [!] Error parsing price '{raw_price}': {e}")
        return raw_price, None, None


def validate_and_fix_dates(df):
    """Fixes common date issues in the dataframe"""
    today = pd.Timestamp.now().floor('D')
    
    # Convert to datetime if not already
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['Valid_Until'] = pd.to_datetime(df['Valid_Until'], errors='coerce')
    
    # Fix: If valid_until is before date, it's wrong - use date + 7 days
    mask = df['Valid_Until'] < df['Date']
    if mask.sum() > 0:
        print(f"   🔧 Fixed {mask.sum()} deals with invalid expiry dates")
        df.loc[mask, 'Valid_Until'] = df.loc[mask, 'Date'] + timedelta(days=7)
    
    # Fix: Missing valid_until dates - assume 7 days from scrape date
    mask = df['Valid_Until'].isna()
    if mask.sum() > 0:
        print(f"   🔧 Added expiry dates to {mask.sum()} deals (7 days from flyer date)")
        df.loc[mask, 'Valid_Until'] = df.loc[mask, 'Date'] + timedelta(days=7)
    
    # Fix: If date is in the future (shouldn't happen), set to today
    mask = df['Date'] > today
    if mask.sum() > 0:
        print(f"   🔧 Fixed {mask.sum()} deals with future dates")
        df.loc[mask, 'Date'] = today
    
    # Info: Log how many deals are already expired
    expired = (df['Valid_Until'] < today).sum()
    if expired > 0:
        print(f"   ℹ️  Note: {expired} deals are already expired")
    
    return df

# --- 4. MAIN SCRAPER LOGIC ---
print("=" * 80)
print("🛒 CALGARY GROCERY DEAL SCRAPER v5")
print("=" * 80)
print(f"\n>> Scanning flyers for postal code: {POSTAL_CODE}...")

flyers = get_active_flyers(POSTAL_CODE)
if not flyers:
    print("[!] No flyers found.")
    exit()

print(f"   Found {len(flyers)} total flyers in your area")

# First pass: Filter out excluded merchants and find matches
selected_flyers = []
excluded_count = 0

for store in STORES:
    print(f"\n🔍 Looking for: {store}")
    matches = []
    
    for f in flyers:
        merchant = f.get('merchant', '')
        
        # Skip if merchant is in exclusion list
        if is_excluded_merchant(merchant):
            excluded_count += 1
            continue
        
        # Check if this merchant matches our target store
        if store.lower() in merchant.lower():
            matches.append(f)
    
    if not matches:
        print(f"   ⚠️  No flyers found for {store}")
        continue
    
    # CRITICAL FIX: Select the flyer with the LATEST end date (most current)
    # This ensures we always get the newest flyer, not just the first "weekly" one
    best = max(matches, key=lambda f: f.get('valid_to', ''))
    
    selected_flyers.append(best)
    print(f"   ✅ Selected: {best['merchant']}")
    print(f"      Name: {best.get('name')}")
    print(f"      Valid: {best.get('valid_from')} to {best.get('valid_to')}")
    print(f"      ID: {best.get('id')}")

print(f"\n📊 Summary:")
print(f"   Total flyers available: {len(flyers)}")
print(f"   Excluded (liquor/pharmacy): {excluded_count}")
print(f"   Selected for scraping: {len(selected_flyers)}")

if not selected_flyers:
    print("\n[!] No valid flyers selected. Exiting.")
    exit()

# --- 5. EXTRACT ITEMS ---
new_deals = []
print("\n>> Extracting items from flyers...")

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
                'Normalized_Price': normalized,  # NEW - shows $/kg for weight items
                'Valid_Until': item.get('valid_to') or flyer.get('valid_to')
            })

print(f"\n>> Total items extracted: {len(new_deals)}")

# --- 6. RUN AI QUALITY ANALYSIS ON NEW ITEMS ONLY ---
if new_deals:
    df_new = pd.DataFrame(new_deals)
    df_new['Item'] = df_new['Item'].astype(str).str.title()
    
    # Load historical archive for context
    if os.path.exists(HISTORICAL_ARCHIVE):
        df_archive = pd.read_csv(HISTORICAL_ARCHIVE)
        # Handle mixed date formats (some with time, some without)
        df_archive['Date'] = pd.to_datetime(df_archive['Date'], format='mixed', errors='coerce')
        print(f"   Using {len(df_archive):,} historical records for context")
        
        # OPTIMIZATION: Identify items already in archive BEFORE AI analysis
        # Create duplicate detection key
        df_new['_dup_key'] = (df_new['Store'] + '|' + df_new['Original_Name'] + '|' + 
                              df_new['Price_Text'] + '|' + df_new['Valid_Until'].astype(str))
        df_archive['_dup_key'] = (df_archive['Store'] + '|' + df_archive['Original_Name'] + '|' + 
                                  df_archive['Price_Text'] + '|' + df_archive['Valid_Until'].astype(str))
        
        # Split into new vs already-analyzed items
        existing_keys = set(df_archive['_dup_key'])
        mask_new = ~df_new['_dup_key'].isin(existing_keys)
        
        items_to_analyze = df_new[mask_new].copy().drop(columns=['_dup_key'])
        items_already_done = df_new[~mask_new].copy()
        
        print(f"\n📊 Analysis Plan:")
        print(f"   🆕 NEW items to analyze: {len(items_to_analyze):,}")
        print(f"   ♻️  Already analyzed (will reuse): {len(items_already_done):,}")
        print(f"   💰 AI cost saved: ~${len(items_already_done) * 0.0002:.2f}")
        
        # For already-analyzed items, get their AI columns from archive
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
        print(f"   No historical data - creating new archive")
    
    # --- PDF GROUND TRUTH EXTRACTION (before AI analysis) ---
    pdf_context = None
    if pdf_verification_enabled():
        print("\n🔍 PDF validation enabled - extracting ground truth...")
        df_new, pdf_context = verify_with_pdfs(df_new)
        
        # Re-split after PDF enhancement
        if len(df_archive) > 0:
            df_new['_dup_key'] = (df_new['Store'] + '|' + df_new['Original_Name'] + '|' + 
                                  df_new['Price_Text'] + '|' + df_new['Valid_Until'].astype(str))
            existing_keys = set(df_archive['_dup_key'])
            mask_new = ~df_new['_dup_key'].isin(existing_keys)
            
            items_to_analyze = df_new[mask_new].copy().drop(columns=['_dup_key'])
            items_already_done = df_new[~mask_new].copy()
            
            if len(items_already_done) > 0:
                ai_columns = [c for c in df_archive.columns if c.startswith('ai_')]
                merge_on = ['Store', 'Original_Name', 'Price_Text', 'Valid_Until']
                
                items_already_done = items_already_done.drop(columns=['_dup_key']).merge(
                    df_archive[merge_on + ai_columns],
                    on=merge_on,
                    how='left'
                )
        else:
            items_to_analyze = df_new.copy()
            items_already_done = pd.DataFrame()
    
    # HEALTH FIX #1: Fill missing subcategories
    if 'ai_sub_category' in df_new.columns:
        missing_before = df_new['ai_sub_category'].isna().sum()
        df_new['ai_sub_category'] = df_new['ai_sub_category'].fillna(df_new.get('ai_category', 'Other'))
        if missing_before > 0:
            print(f"\n✅ Health Fix: Filled {missing_before} missing subcategories")
    
    # Run AI analysis ONLY on truly new items
    if len(items_to_analyze) > 0:
        print(f"\n>> Running AI quality analysis on {len(items_to_analyze)} NEW items...")
        try:
            # Pass PDF context to AI if available
            if pdf_context:
                print(f"   🤖 Enhanced with PDF context from {len(pdf_context)} stores")
                items_to_analyze = add_ai_analysis_to_dataframe(
                    items_to_analyze, df_archive, 
                    batch_size=50, pdf_context=pdf_context
                )
            else:
                items_to_analyze = add_ai_analysis_to_dataframe(
                    items_to_analyze, df_archive, 
                    batch_size=50
                )
        except Exception as e:
            print(f"   [!] AI analysis failed: {e}")
            print(f"   Continuing without AI enhancements...")
    else:
        print(f"\n✅ No new items to analyze - all {len(items_already_done)} items already in archive!")
    
    # Recombine: newly analyzed + already analyzed
    if len(items_already_done) > 0:
        df_new = pd.concat([items_to_analyze, items_already_done], ignore_index=True)
    else:
        df_new = items_to_analyze
    
    # --- SAVE TO HISTORICAL ARCHIVE ---
    if len(df_archive) > 0:
        # Append new deals
        df_archive = pd.concat([df_archive, df_new], ignore_index=True)
        
        # HEALTH FIX #2: Improved deduplication (by Store, Item, Price, Date)
        before = len(df_archive)
        df_archive.drop_duplicates(
            subset=['Store', 'Item', 'Price_Value', 'Date'],
            keep='last',  # Keep most recent
            inplace=True
        )
        after = len(df_archive)
        
        if before > after:
            print(f"\n✅ Health Fix: Removed {before - after:,} duplicate records")
    else:
        df_archive = df_new.copy()
    
    print(f"\n>> Historical archive updated: {len(df_archive):,} total records")
    df_archive.to_csv(HISTORICAL_ARCHIVE, index=False)
    
    # --- CREATE CURRENT FLYERS FILE ---
    # This is just the latest scrape
    df_current = df_new.copy()
    df_current.to_csv(CURRENT_FLYERS, index=False)
    print(f">> Current flyers saved: {len(df_current):,} active deals")
    
    # Backwards compatibility - save as clean_grocery_data.csv too
    df_current.to_csv(DASHBOARD_FILE, index=False)
    print(f">> Dashboard file saved: {DASHBOARD_FILE}")
    
    # --- VERIFICATION STATS ---
    print("\n" + "=" * 80)
    print("📈 SCRAPE STATISTICS")
    print("=" * 80)
    
    print("\nItems per store:")
    store_counts = df_new['Store'].value_counts()
    for store, count in store_counts.items():
        print(f"   {store}: {count} items")
    
    print("\nPrice distribution:")
    print(f"   Items with prices: {(df_new['Price_Value'] > 0).sum()}")
    print(f"   Items without prices: {(df_new['Price_Value'] == 0).sum()}")
    if (df_new['Price_Value'] > 0).sum() > 0:
        print(f"   Average price: ${df_new[df_new['Price_Value'] > 0]['Price_Value'].mean():.2f}")
    
    # Check for Sobeys specifically
    sobeys_items = df_new[df_new['Store'].str.contains('Sobeys', case=False, na=False)]
    safeway_items = df_new[df_new['Store'].str.contains('Safeway', case=False, na=False)]
    
    if len(sobeys_items) > 0:
        print(f"\n✅ Sobeys verification:")
        print(f"   Items: {len(sobeys_items)}")
        print(f"   Sample items: {sobeys_items['Item'].head(5).tolist()}")
    
    if len(safeway_items) > 0:
        print(f"\n✅ Safeway verification:")
        print(f"   Items: {len(safeway_items)}")
        print(f"   Sample items: {safeway_items['Item'].head(5).tolist()}")

else:
    print("[!] No items found.")
    
print("\n" + "=" * 80)
print("✅ SCRAPE COMPLETE!")
print("=" * 80)
print("\n💡 Next steps:")
print("   1. Check current_flyers.csv for latest deals")

# Check if PDF validation ran
if pdf_verification_enabled() and 'is_member_exclusive' in df_current.columns:
    member_count = df_current['is_member_exclusive'].sum()
    validated_count = df_current.get('pdf_matched', pd.Series()).sum()
    
    if member_count > 0:
        print(f"   2. PDF Validation Results:")
        print(f"      ✅ {validated_count} items validated against PDFs")
        print(f"      🎫 {member_count} member exclusives found!")
        print(f"      📁 Check member_exclusive_items.csv for details")
        print("   3. Run dashboard.py to view the data")
    else:
        print("   2. Run dashboard.py to view the data")
else:
    print("   2. Run dashboard.py to view the data")
    if not pdf_verification_enabled():
        print("   💡 Add PDFs to 'flyers/' folder + GEMINI_API_KEY to enable validation")

print("   4. Run generate_facebook_post.py for social media content")
print("=" * 80)
