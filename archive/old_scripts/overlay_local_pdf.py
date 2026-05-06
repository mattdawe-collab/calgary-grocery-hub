"""
Local PDF Flyer Overlay System
Uses PDFs you've already downloaded to your Flyers folder
Overlays AI badges on the actual flyer pages
"""

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import json
import os
from datetime import datetime
import fitz  # PyMuPDF

class LocalPDFOverlay:
    """Overlay AI badges on local PDF flyers"""
    
    def __init__(self):
        self.flyer_data = None
        self.items_by_page = {}
        self.flyers_folder = "Flyers"
    
    def load_flyer_json(self, json_file):
        """Load flyer JSON"""
        with open(json_file, 'r') as f:
            self.flyer_data = json.load(f)
    
    def find_matching_pdf(self, store_name, date_range=None):
        """Find matching PDF in Flyers folder"""
        
        if not os.path.exists(self.flyers_folder):
            print(f"❌ Flyers folder not found: {self.flyers_folder}")
            return None
        
        # List all PDFs
        pdfs = [f for f in os.listdir(self.flyers_folder) if f.lower().endswith('.pdf')]
        
        if not pdfs:
            print(f"❌ No PDFs found in {self.flyers_folder}")
            return None
        
        print(f"\n📂 Found {len(pdfs)} PDFs in Flyers folder:")
        for pdf in pdfs:
            print(f"   • {pdf}")
        
        # Find best match based on store name
        store_keywords = {
            'safeway': ['safeway', 'sobeys'],  # Often same flyer
            'sobeys': ['sobeys', 'safeway'],
            'superstore': ['superstore', 'super'],
            'co-op': ['co-op', 'coop'],
            'no frills': ['no frills', 'nofrills', 'frills'],
            'save-on': ['save-on', 'saveon'],
        }
        
        store_lower = store_name.lower()
        keywords = store_keywords.get(store_lower, [store_lower])
        
        # Find matches
        matches = []
        for pdf in pdfs:
            pdf_lower = pdf.lower()
            for keyword in keywords:
                if keyword in pdf_lower:
                    matches.append(pdf)
                    break
        
        if not matches:
            print(f"\n⚠️  No PDF matches found for '{store_name}'")
            print(f"   Available PDFs: {', '.join(pdfs[:5])}")
            return None
        
        # Get most recent
        matches.sort(reverse=True)
        selected = matches[0]
        
        print(f"\n✅ Selected PDF: {selected}")
        
        return os.path.join(self.flyers_folder, selected)
    
    def map_items_to_pages(self):
        """Map items to PDF pages"""
        pages = self.flyer_data['pages']
        items = self.flyer_data['items']
        
        for page in pages:
            self.items_by_page[page['page']] = {
                'bounds': page,
                'items': []
            }
        
        for item in items:
            item_center_x = (item['left'] + item['right']) / 2
            item_center_y = (item['top'] + item['bottom']) / 2
            
            for page in pages:
                if (page['left'] <= item_center_x <= page['right'] and
                    page['bottom'] <= item_center_y <= page['top']):
                    self.items_by_page[page['page']]['items'].append(item)
                    break
    
    def create_ai_badge(self, score, rating, size=70):
        """Create AI badge"""
        badge = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        
        colors = {
            'excellent': (46, 204, 113),
            'very_good': (39, 174, 96),
            'good': (52, 152, 219),
            'fair': (243, 156, 18),
            'poor': (231, 76, 60),
            'not_a_deal': (149, 165, 166),
        }
        
        color = colors.get(rating, (149, 165, 166))
        
        # Shadow
        draw.ellipse([4, 4, size-1, size-1], fill=(0, 0, 0, 120))
        
        # Circle with thick white border
        draw.ellipse([0, 0, size-5, size-5], fill=color, outline=(255, 255, 255), width=5)
        
        # Score text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.45))
        except:
            try:
                font = ImageFont.truetype("arial.ttf", int(size * 0.45))
            except:
                font = ImageFont.load_default()
        
        text = str(score)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        draw.text(((size-tw)//2-2, (size-th)//2-4), text, fill=(255, 255, 255), font=font)
        
        return badge
    
    def transform_coords(self, item, page_bounds, img_width, img_height):
        """Transform Flipp coordinates to image pixel coordinates"""
        
        flipp_left = page_bounds['left']
        flipp_right = page_bounds['right']
        flipp_top = page_bounds['top']
        flipp_bottom = page_bounds['bottom']
        
        flipp_width = flipp_right - flipp_left
        flipp_height = flipp_top - flipp_bottom
        
        # Item center
        item_center_x = (item['left'] + item['right']) / 2
        item_center_y = (item['top'] + item['bottom']) / 2
        
        # Relative position
        rel_x = (item_center_x - flipp_left) / flipp_width
        rel_y = (flipp_top - item_center_y) / flipp_height
        
        # Pixel coordinates
        pixel_x = int(rel_x * img_width)
        pixel_y = int(rel_y * img_height)
        
        # Item size
        item_width = int((item['right'] - item['left']) / flipp_width * img_width)
        item_height = int((item['top'] - item['bottom']) / flipp_height * img_height)
        
        return {
            'x': pixel_x,
            'y': pixel_y,
            'width': item_width,
            'height': item_height
        }
    
    def overlay_badges_on_pdf(self, pdf_path, ai_matches, dpi=150, max_pages=15):
        """Overlay AI badges on PDF"""
        
        print(f"\n🎨 Processing PDF: {os.path.basename(pdf_path)}")
        
        # Open PDF
        pdf_doc = fitz.open(pdf_path)
        
        print(f"   PDF has {len(pdf_doc)} pages")
        
        # Map items to pages
        self.map_items_to_pages()
        
        enhanced_pages = []
        
        for page_num in range(1, min(len(pdf_doc) + 1, max_pages + 1)):
            
            page_data = self.items_by_page.get(page_num)
            
            # Render page to image
            page = pdf_doc[page_num - 1]
            pix = page.get_pixmap(dpi=dpi)
            page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            if not page_data or not page_data['items']:
                # No items, just add page as-is
                enhanced_pages.append(page_img)
                continue
            
            print(f"\n   📄 Page {page_num} ({len(page_data['items'])} items):")
            
            # Convert to RGBA
            page_img = page_img.convert('RGBA')
            overlay = Image.new('RGBA', page_img.size, (0, 0, 0, 0))
            
            badges_added = 0
            
            # Add badges
            for item in page_data['items']:
                item_name = item['name']
                
                if item_name not in ai_matches:
                    continue
                
                ai_data = ai_matches[item_name]
                score = ai_data['score']
                
                if score < 50:  # Only show good deals
                    continue
                
                # Transform coordinates
                coords = self.transform_coords(
                    item,
                    page_data['bounds'],
                    page_img.width,
                    page_img.height
                )
                
                # Badge size based on item size
                badge_size = min(100, int(coords['width'] * 0.35))
                badge_size = max(50, badge_size)
                
                badge = self.create_ai_badge(score, ai_data['rating'], badge_size)
                
                # Position at top-right of item
                badge_x = coords['x'] + coords['width'] // 2 - badge_size - 10
                badge_y = coords['y'] - coords['height'] // 2 + 10
                
                # Clamp
                badge_x = max(0, min(badge_x, page_img.width - badge_size))
                badge_y = max(0, min(badge_y, page_img.height - badge_size))
                
                overlay.paste(badge, (badge_x, badge_y), badge)
                badges_added += 1
            
            # Composite
            result = Image.alpha_composite(page_img, overlay)
            enhanced_pages.append(result.convert('RGB'))
            
            print(f"      ✅ Added {badges_added} AI badges")
        
        pdf_doc.close()
        
        return enhanced_pages
    
    def generate(self, json_file, csv_file, store_name="Safeway", dpi=150, max_pages=15):
        """Generate enhanced PDF from local files"""
        
        print("\n" + "=" * 70)
        print(f"📄 LOCAL PDF OVERLAY GENERATOR - {store_name}")
        print("=" * 70)
        
        # Load flyer JSON
        print(f"\n📥 Loading flyer data...")
        self.load_flyer_json(json_file)
        
        flyer_id = self.flyer_data['items'][0]['flyer_id']
        print(f"   Flyer ID: {flyer_id}")
        print(f"   Items: {len(self.flyer_data['items'])}")
        
        # Find matching PDF
        pdf_path = self.find_matching_pdf(store_name)
        
        if not pdf_path:
            return None
        
        # Load AI scores
        print(f"\n📊 Loading AI scores from {csv_file}...")
        
        if not os.path.exists(csv_file):
            print(f"   ⚠️  {csv_file} not found")
            ai_matches = {}
        else:
            df = pd.read_csv(csv_file)
            df = df[df['Store'].str.contains(store_name, case=False, na=False)]
            
            ai_matches = {}
            for _, row in df.iterrows():
                if pd.notna(row.get('ai_deal_score')) and row['ai_deal_score'] > 0:
                    ai_matches[row['Item']] = {
                        'score': int(row['ai_deal_score']),
                        'rating': row.get('ai_deal_rating', 'not_a_deal')
                    }
            
            print(f"   Loaded {len(ai_matches)} items with AI scores")
        
        # Process PDF
        enhanced_pages = self.overlay_badges_on_pdf(pdf_path, ai_matches, dpi, max_pages)
        
        if not enhanced_pages:
            print(f"\n❌ No pages generated")
            return None
        
        # Save
        print(f"\n💾 Saving enhanced PDF...")
        
        output_file = f"AI_Enhanced_{store_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        enhanced_pages[0].save(
            output_file,
            save_all=True,
            append_images=enhanced_pages[1:] if len(enhanced_pages) > 1 else [],
            format='PDF',
            resolution=dpi
        )
        
        print(f"\n✅ SUCCESS!")
        print(f"📄 Saved: {output_file}")
        print(f"📊 {len(enhanced_pages)} pages with AI overlays")
        print(f"🎯 Resolution: {dpi} DPI")
        print("=" * 70)
        
        return output_file


if __name__ == "__main__":
    overlay = LocalPDFOverlay()
    
    # Generate enhanced flyer using local PDF
    overlay.generate(
        json_file="sobeys_flyer_data_20251223_084608.json",
        csv_file="current_flyers.csv",
        store_name="Safeway",  # or "Sobeys" - will find matching PDF
        dpi=150,  # Higher = better quality but larger file
        max_pages=15  # How many pages to process
    )
