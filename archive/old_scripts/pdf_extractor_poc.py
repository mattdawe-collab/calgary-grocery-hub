"""
PROOF OF CONCEPT: PDF Grocery Deal Extractor
Uses Gemini 3.0 Pro Vision to extract deals from Sobeys flyer PDF

REQUIREMENTS:
    pip install google-generativeai PyMuPDF pandas pillow python-dotenv --break-system-packages

USAGE:
    python pdf_extractor_poc.py
"""

import os
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image
import io

# ============================================================================
# CONFIGURATION
# ============================================================================

# Load environment variables from .env file (same as get_deals.py)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Get API key from environment variable
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file")
    print("Please add to your .env file:")
    print("GEMINI_API_KEY=your-key-here")
    exit(1)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Input/Output
PDF_PATH = "Sobeys_Dec_24-31.pdf"  # Your uploaded Sobeys flyer
OUTPUT_CSV = "sobeys_extracted_deals.csv"
OUTPUT_JSON = "sobeys_extracted_deals.json"

# Model settings
MODEL_NAME = "gemini-3-pro-preview-11-2025"  # Latest and best! (Nov 2025)
# Alternative faster option:
# MODEL_NAME = "gemini-2.0-flash-exp"  # Faster/cheaper but less accurate

# Processing options
MAX_PAGES = None  # None = all pages, or set to 3 for quick test
IMAGE_DPI = 150  # DPI for PDF->Image conversion (higher = better quality, slower)

# ============================================================================
# EXTRACTION PROMPT
# ============================================================================

EXTRACTION_PROMPT = """You are a precise grocery deal extraction AI. Analyze this flyer page and extract ALL visible grocery items with prices.

**INSTRUCTIONS:**
1. Extract EVERY item you can see with a price
2. For each item, provide:
   - name: Full product name exactly as shown
   - price_text: Exact price text (e.g., "$9.99", "$5.99/lb", "2/$5")
   - price_value: Numeric price for ONE unit (calculate if multi-buy)
   - unit: "each", "lb", "kg", "100g", or specific unit shown
   - category: "Meat", "Produce", "Dairy", "Bakery", "Seafood", "Frozen", "Pantry", "Snacks", "Beverages", "Other"
   - brand: Brand name if visible, otherwise "Unknown"
   - confidence: 0.0-1.0 (how confident you are in this extraction)

3. **CRITICAL RULES:**
   - If price is per weight ($/lb, $/kg), extract the UNIT price, not total
   - If multi-buy (2 for $5), calculate single unit price ($2.50)
   - If "Buy X Get Y Free", calculate effective unit price
   - If you're unsure about ANY field, set confidence < 0.8
   - Skip items without visible prices
   - Skip non-grocery items (ads, store info, etc.)

4. **OUTPUT FORMAT:**
   Return ONLY a valid JSON array. No markdown, no explanation, just:
   [
     {
       "name": "Maple Leaf Bacon",
       "price_text": "$3.99",
       "price_value": 3.99,
       "unit": "each",
       "category": "Meat",
       "brand": "Maple Leaf",
       "confidence": 0.95
     },
     ...
   ]

Extract ALL items from this page now:"""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def pdf_to_images(pdf_path, dpi=150, max_pages=None):
    """Convert PDF pages to PIL Images"""
    print(f"\n📄 Converting PDF to images (DPI: {dpi})...")
    
    doc = fitz.open(pdf_path)
    images = []
    
    total_pages = len(doc) if max_pages is None else min(max_pages, len(doc))
    
    for page_num in range(total_pages):
        print(f"   Processing page {page_num + 1}/{total_pages}...", end='\r')
        
        page = doc[page_num]
        # Render page to pixmap (image)
        mat = fitz.Matrix(dpi/72, dpi/72)  # 72 DPI is default
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        images.append(img)
    
    doc.close()
    print(f"\n✅ Converted {len(images)} pages to images")
    return images

def extract_items_from_image(image, page_num, model):
    """Use Gemini Vision to extract items from one page"""
    print(f"\n🤖 Extracting items from page {page_num}...")
    
    try:
        # Send image to Gemini
        response = model.generate_content([
            EXTRACTION_PROMPT,
            image
        ])
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        
        response_text = response_text.strip()
        
        # Parse JSON
        items = json.loads(response_text)
        
        # Add page number to each item
        for item in items:
            item['page'] = page_num
        
        print(f"   ✅ Extracted {len(items)} items")
        return items
        
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON parsing error: {e}")
        print(f"   Response was: {response.text[:200]}...")
        return []
    except Exception as e:
        print(f"   ❌ Extraction error: {e}")
        return []

def validate_items(items):
    """Add validation flags and statistics"""
    print(f"\n🔍 Validating {len(items)} extracted items...")
    
    flagged = []
    stats = {
        'total': len(items),
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'needs_review': 0
    }
    
    for item in items:
        # Calculate validation flags
        confidence = item.get('confidence', 0.5)
        price_value = item.get('price_value', 0)
        
        item['needs_review'] = False
        item['validation_issues'] = []
        
        # Flag 1: Low confidence
        if confidence < 0.8:
            item['needs_review'] = True
            item['validation_issues'].append(f"Low AI confidence ({confidence:.2f})")
        
        # Flag 2: Suspicious price (too high or too low)
        if price_value > 100:
            item['needs_review'] = True
            item['validation_issues'].append(f"Unusually high price (${price_value:.2f})")
        elif price_value < 0.1 and price_value > 0:
            item['needs_review'] = True
            item['validation_issues'].append(f"Unusually low price (${price_value:.2f})")
        
        # Flag 3: Missing required fields
        if not item.get('name'):
            item['needs_review'] = True
            item['validation_issues'].append("Missing product name")
        
        # Count confidence levels
        if confidence >= 0.9:
            stats['high_confidence'] += 1
        elif confidence >= 0.7:
            stats['medium_confidence'] += 1
        else:
            stats['low_confidence'] += 1
        
        if item['needs_review']:
            stats['needs_review'] += 1
            flagged.append(item)
    
    print(f"\n📊 Validation Statistics:")
    print(f"   Total items: {stats['total']}")
    print(f"   High confidence (≥90%): {stats['high_confidence']} ({stats['high_confidence']/stats['total']*100:.1f}%)")
    print(f"   Medium confidence (70-90%): {stats['medium_confidence']} ({stats['medium_confidence']/stats['total']*100:.1f}%)")
    print(f"   Low confidence (<70%): {stats['low_confidence']} ({stats['low_confidence']/stats['total']*100:.1f}%)")
    print(f"   🚩 Flagged for review: {stats['needs_review']} ({stats['needs_review']/stats['total']*100:.1f}%)")
    
    return items, flagged, stats

def save_results(items, flagged_items):
    """Save extracted items to CSV and JSON"""
    print(f"\n💾 Saving results...")
    
    # Convert to DataFrame
    df = pd.DataFrame(items)
    
    # Add metadata
    df['extraction_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df['source_pdf'] = PDF_PATH
    
    # Reorder columns for readability
    cols = ['page', 'name', 'price_text', 'price_value', 'unit', 'category', 'brand', 
            'confidence', 'needs_review', 'validation_issues', 'extraction_date', 'source_pdf']
    df = df[cols]
    
    # Save to CSV
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"   ✅ Saved to CSV: {OUTPUT_CSV}")
    
    # Save to JSON (easier for manual review)
    with open(OUTPUT_JSON, 'w') as f:
        json.dump({
            'metadata': {
                'source_pdf': PDF_PATH,
                'extraction_date': datetime.now().isoformat(),
                'total_items': len(items),
                'model_used': MODEL_NAME
            },
            'items': items,
            'flagged_for_review': flagged_items
        }, f, indent=2)
    print(f"   ✅ Saved to JSON: {OUTPUT_JSON}")
    
    return df

def display_sample_items(df, n=10):
    """Display sample of extracted items"""
    print(f"\n📋 Sample of extracted items (first {n}):")
    print("=" * 100)
    
    for idx, row in df.head(n).iterrows():
        confidence_emoji = "✅" if row['confidence'] >= 0.9 else "⚠️" if row['confidence'] >= 0.7 else "❌"
        print(f"{confidence_emoji} Page {row['page']}: {row['name']}")
        print(f"   Price: {row['price_text']} (${row['price_value']:.2f}/{row['unit']})")
        print(f"   Category: {row['category']} | Brand: {row['brand']}")
        print(f"   Confidence: {row['confidence']:.0%}")
        if row['needs_review']:
            print(f"   🚩 REVIEW: {', '.join(row['validation_issues'])}")
        print()

def display_flagged_items(flagged_items):
    """Display items that need human review"""
    if not flagged_items:
        print("\n🎉 No items flagged for review! All extractions look good.")
        return
    
    print(f"\n⚠️  ITEMS FLAGGED FOR REVIEW ({len(flagged_items)} items):")
    print("=" * 100)
    
    for item in flagged_items[:20]:  # Show first 20
        print(f"📄 Page {item['page']}: {item.get('name', 'MISSING NAME')}")
        print(f"   Price: {item.get('price_text', 'N/A')} → ${item.get('price_value', 0):.2f}")
        print(f"   Confidence: {item.get('confidence', 0):.0%}")
        print(f"   Issues: {', '.join(item.get('validation_issues', []))}")
        print()
    
    if len(flagged_items) > 20:
        print(f"   ... and {len(flagged_items) - 20} more items")
        print(f"   See full list in: {OUTPUT_JSON}")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("=" * 100)
    print("🛒 GROCERY PDF EXTRACTOR - PROOF OF CONCEPT")
    print("=" * 100)
    
    # Check if PDF exists
    if not os.path.exists(PDF_PATH):
        print(f"\n❌ ERROR: PDF file not found: {PDF_PATH}")
        print("Please make sure the Sobeys flyer PDF is in the current directory.")
        return
    
    # Initialize Gemini model
    print(f"\n🤖 Initializing Gemini model: {MODEL_NAME}")
    model = genai.GenerativeModel(MODEL_NAME)
    
    # Step 1: Convert PDF to images
    images = pdf_to_images(PDF_PATH, dpi=IMAGE_DPI, max_pages=MAX_PAGES)
    
    # Step 2: Extract items from each page
    all_items = []
    for page_num, image in enumerate(images, start=1):
        items = extract_items_from_image(image, page_num, model)
        all_items.extend(items)
    
    if not all_items:
        print("\n❌ No items extracted. Check the PDF or try a different model.")
        return
    
    print(f"\n✅ Total items extracted: {len(all_items)}")
    
    # Step 3: Validate and flag items
    validated_items, flagged_items, stats = validate_items(all_items)
    
    # Step 4: Save results
    df = save_results(validated_items, flagged_items)
    
    # Step 5: Display results
    display_sample_items(df, n=10)
    display_flagged_items(flagged_items)
    
    # Final summary
    print("\n" + "=" * 100)
    print("✅ EXTRACTION COMPLETE!")
    print("=" * 100)
    print(f"\n📊 Summary:")
    print(f"   Pages processed: {len(images)}")
    print(f"   Items extracted: {len(all_items)}")
    print(f"   High confidence: {stats['high_confidence']} ({stats['high_confidence']/stats['total']*100:.1f}%)")
    print(f"   Needs review: {stats['needs_review']} ({stats['needs_review']/stats['total']*100:.1f}%)")
    print(f"\n📁 Output files:")
    print(f"   CSV: {OUTPUT_CSV}")
    print(f"   JSON: {OUTPUT_JSON}")
    print(f"\n💡 Next steps:")
    print(f"   1. Review flagged items in {OUTPUT_JSON}")
    print(f"   2. Compare with Flipp API results")
    print(f"   3. Adjust confidence thresholds if needed")
    print(f"   4. Run on other flyers to test scalability")
    print("=" * 100)

if __name__ == "__main__":
    main()
