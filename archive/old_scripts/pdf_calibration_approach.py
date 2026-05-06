# PDF CALIBRATION APPROACH - The Right Architecture
# ====================================================
# 
# PHILOSOPHY: API is truth. PDF provides calibration signals.
# Don't try to extract every item - that's what the API is for!
#
# ====================================================

def extract_calibration_signals(images, store_name):
    """
    Extract CALIBRATION SIGNALS from PDF, not complete item list.
    
    Returns:
    - Member pricing indicators (which pages, which items)
    - Visual prominence signals (featured items, hot deals)
    - Price spot-checks (validate API against 20-30 visible prices)
    - Layout context (what's emphasized, what's buried)
    """
    
    calibration_data = {
        'store': store_name,
        'member_indicators': [],      # Items with member badges
        'featured_items': [],          # Visually prominent items
        'spot_check_prices': [],       # Sample of prices for validation
        'visual_hierarchy': {},        # What's emphasized per page
        'total_pages': len(images)
    }
    
    for page_num, img in enumerate(images, 1):
        
        # FOCUSED PROMPT: Don't ask for everything, ask for SIGNALS
        prompt = f"""Analyze this grocery flyer page {page_num} for visual signals.

1. MEMBER PRICING: List any items with these indicators:
   - "Member Price", "Club Price", "MyOffers"
   - Membership badges or special icons
   Format: ItemName | Price

2. FEATURED DEALS: List items that are visually prominent:
   - Large displays, red circles, hot deal badges
   - Top of page, large font, bright colors
   Format: ItemName | Price

3. SPOT CHECK: List 5-10 random prices you see for validation:
   Format: ItemName | Price

Keep responses SHORT. We're calibrating, not extracting everything."""

        try:
            model = genai.GenerativeModel('gemini-3-flash-preview')
            buffered = io.BytesIO()
            img.save(buffered, format="PNG", optimize=True, quality=95)
            
            response = model.generate_content(
                [prompt, {'mime_type': 'image/png', 'data': buffered.getvalue()}],
                generation_config={
                    'temperature': 0.7,
                    'max_output_tokens': 2000  # SHORT responses
                }
            )
            
            # Parse response (simple text parsing, not strict)
            response_text = response.text.strip()
            
            # Extract member items (look for section headers in response)
            if 'MEMBER' in response_text.upper():
                member_section = extract_section(response_text, 'MEMBER')
                for line in member_section.split('\n'):
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            calibration_data['member_indicators'].append({
                                'name': parts[0].strip(),
                                'price': parts[1].strip(),
                                'page': page_num
                            })
            
            # Extract featured items
            if 'FEATURED' in response_text.upper():
                featured_section = extract_section(response_text, 'FEATURED')
                for line in featured_section.split('\n'):
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            calibration_data['featured_items'].append({
                                'name': parts[0].strip(),
                                'price': parts[1].strip(),
                                'page': page_num,
                                'prominence': 'high'
                            })
            
            # Extract spot check prices
            if 'SPOT CHECK' in response_text.upper():
                spot_section = extract_section(response_text, 'SPOT CHECK')
                for line in spot_section.split('\n'):
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            calibration_data['spot_check_prices'].append({
                                'name': parts[0].strip(),
                                'price': parts[1].strip(),
                                'page': page_num
                            })
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"      Page {page_num} calibration: {str(e)[:60]}")
            continue
    
    return calibration_data


def extract_section(text, header):
    """Extract text section after a header."""
    lines = text.split('\n')
    section_lines = []
    in_section = False
    
    for line in lines:
        if header in line.upper():
            in_section = True
            continue
        if in_section:
            if line.strip() and not line[0].isdigit() and ':' not in line:
                # New section starting
                if any(keyword in line.upper() for keyword in ['MEMBER', 'FEATURED', 'SPOT']):
                    break
            section_lines.append(line)
    
    return '\n'.join(section_lines)


def calibrate_api_with_pdf(api_items, calibration_signals):
    """
    Enhance API items with PDF calibration signals.
    """
    
    print(f"\n📊 CALIBRATING API DATA WITH PDF SIGNALS")
    print(f"   Member indicators found: {len(calibration_signals['member_indicators'])}")
    print(f"   Featured items found: {len(calibration_signals['featured_items'])}")
    print(f"   Spot check samples: {len(calibration_signals['spot_check_prices'])}")
    
    calibrated_items = []
    
    for api_item in api_items:
        enhanced = api_item.copy()
        api_name_lower = api_item['Item'].lower()
        
        # Check for member pricing signal
        for member_item in calibration_signals['member_indicators']:
            member_name_lower = member_item['name'].lower()
            # Fuzzy match (check if significant overlap)
            if fuzzy_match(api_name_lower, member_name_lower):
                enhanced['is_member_exclusive'] = True
                enhanced['member_indicator'] = 'Member Price'
                enhanced['pdf_calibration'] = 'member_detected'
                break
        
        # Check for featured status
        for featured_item in calibration_signals['featured_items']:
            featured_name_lower = featured_item['name'].lower()
            if fuzzy_match(api_name_lower, featured_name_lower):
                enhanced['is_featured'] = True
                enhanced['visual_prominence'] = 'high'
                enhanced['pdf_page'] = featured_item['page']
                enhanced['pdf_calibration'] = 'featured_detected'
                break
        
        # Spot check price validation
        for spot_item in calibration_signals['spot_check_prices']:
            spot_name_lower = spot_item['name'].lower()
            if fuzzy_match(api_name_lower, spot_name_lower):
                pdf_price = extract_price_value(spot_item['price'])
                api_price = float(api_item.get('Price_Value', 0))
                
                if pdf_price and abs(api_price - pdf_price) < 0.10:
                    enhanced['price_validated'] = True
                    enhanced['pdf_calibration'] = 'price_verified'
                elif pdf_price and abs(api_price - pdf_price) > 1.00:
                    enhanced['price_mismatch'] = True
                    enhanced['pdf_price'] = pdf_price
                    enhanced['pdf_calibration'] = 'price_discrepancy'
                break
        
        calibrated_items.append(enhanced)
    
    # Statistics
    member_count = sum(1 for item in calibrated_items if item.get('is_member_exclusive'))
    featured_count = sum(1 for item in calibrated_items if item.get('is_featured'))
    validated_count = sum(1 for item in calibrated_items if item.get('price_validated'))
    mismatches = sum(1 for item in calibrated_items if item.get('price_mismatch'))
    
    print(f"\n✅ CALIBRATION RESULTS:")
    print(f"   {member_count} items marked as member exclusive")
    print(f"   {featured_count} items marked as featured")
    print(f"   {validated_count} prices validated")
    print(f"   {mismatches} price discrepancies flagged")
    
    return calibrated_items


def fuzzy_match(str1, str2, threshold=0.6):
    """Simple fuzzy string matching."""
    # Extract significant words (>3 chars)
    words1 = set(w for w in str1.split() if len(w) > 3)
    words2 = set(w for w in str2.split() if len(w) > 3)
    
    if not words1 or not words2:
        return str1 in str2 or str2 in str1
    
    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return (intersection / union) >= threshold if union > 0 else False


def extract_price_value(price_text):
    """Extract numeric price from text."""
    import re
    nums = re.findall(r'\d+\.?\d*', price_text.replace('$', ''))
    return float(nums[0]) if nums else None


# ====================================================
# USAGE IN get_deals.py:
# ====================================================
"""
# After scraping API (1,400 items):
df_api = scrape_api()  # Your existing code

# Extract calibration signals (not full OCR):
if pdf_verification_enabled():
    print("📄 Extracting calibration signals from PDFs...")
    calibration_signals = extract_calibration_signals(images, store)
    
    # Calibrate API with PDF signals:
    df_enhanced = calibrate_api_with_pdf(df_api, calibration_signals)
else:
    df_enhanced = df_api

# Claude gets ENHANCED data (API + calibration):
df_with_ai = add_ai_analysis_to_dataframe(df_enhanced, historical_data)

# Claude now knows:
# - Which items are member exclusive (from PDF)
# - Which items are visually featured (from PDF)  
# - Price validation confidence (from PDF)
# - All the structured API data (complete dataset)
"""

# ====================================================
# BENEFITS OF THIS APPROACH:
# ====================================================
"""
✅ Fast: Only 20-30 items extracted per page vs. trying to get all 40+
✅ Reliable: Focused task = better results
✅ Cheaper: Lower token usage (~$0.03/store vs $0.15)
✅ Smart: Uses API as truth, PDF for intelligence
✅ Scalable: Can handle any number of API items
✅ Robust: Doesn't fail if PDF misses items
✅ Right tool: Gemini 3 for SIGNALS, not pixel-perfect OCR
"""
