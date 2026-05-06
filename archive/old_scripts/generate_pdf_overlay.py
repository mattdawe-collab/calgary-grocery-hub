"""
PDF Flyer Overlay System
Downloads the actual flyer PDF and overlays AI badges
This is the SIMPLEST and BEST approach!
"""

import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import json
import os
from datetime import datetime
from pypdf import PdfReader, PdfWriter
import fitz  # PyMuPDF for PDF rendering

class PDFFlyerOverlay:
    """Overlay AI badges on real PDF flyers"""
    
    def __init__(self):
        self.flyer_id = None
        self.flyer_data = None
        self.items_by_page = {}
    
    def load_flyer_json(self, json_file):
        """Load flyer JSON"""
        with open(json_file, 'r') as f:
            self.flyer_data = json.load(f)
        
        if self.flyer_data['items']:
            self.flyer_id = self.flyer_data['items'][0]['flyer_id']
    
    def download_flyer_pdf(self):
        """Try to download the actual flyer PDF"""
        
        # Try multiple URL patterns
        pdf_urls = [
            f"https://flipp.com/api/flyers/{self.flyer_id}/pdf",
            f"https://da.flippcdn.com/flyers/{self.flyer_id}.pdf",
            f"https://flipp-flyerkit-production.s3.amazonaws.com/flyers/{self.flyer_id}.pdf",
            f"https://backflipp.wishabi.com/flipp/flyers/{self.flyer_id}.pdf",
        ]
        
        for url in pdf_urls:
            print(f"   Trying: {url[:70]}...")
            
            try:
                response = requests.get(url, timeout=15, allow_redirects=True)
                
                if response.status_code == 200 and response.headers.get('Content-Type', '').startswith('application/pdf'):
                    print(f"   ✅ Downloaded PDF! ({len(response.content) / 1024:.0f} KB)")
                    return response.content
                
            except Exception as e:
                continue
        
        print(f"   ❌ Could not download PDF from any URL")
        return None
    
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
    
    def create_ai_badge_pdf(self, score, rating, size=60):
        """Create AI badge as PIL image"""
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
        draw.ellipse([4, 4, size-1, size-1], fill=(0, 0, 0, 100))
        
        # Circle
        draw.ellipse([0, 0, size-5, size-5], fill=color, outline=(255, 255, 255), width=4)
        
        # Score text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.45))
        except:
            font = ImageFont.load_default()
        
        text = str(score)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        draw.text(((size-tw)//2-2, (size-th)//2-4), text, fill=(255, 255, 255), font=font)
        
        return badge
    
    def transform_coords_to_pdf(self, item, page_bounds, pdf_page_height, pdf_page_width):
        """Transform Flipp coordinates to PDF coordinates"""
        
        # Flipp bounds
        flipp_left = page_bounds['left']
        flipp_right = page_bounds['right']
        flipp_top = page_bounds['top']
        flipp_bottom = page_bounds['bottom']
        
        flipp_width = flipp_right - flipp_left
        flipp_height = flipp_top - flipp_bottom
        
        # Item center
        item_center_x = (item['left'] + item['right']) / 2
        item_center_y = (item['top'] + item['bottom']) / 2
        
        # Relative position (0 to 1)
        rel_x = (item_center_x - flipp_left) / flipp_width
        rel_y = (flipp_top - item_center_y) / flipp_height
        
        # PDF coordinates (origin at bottom-left in PDF)
        pdf_x = rel_x * pdf_page_width
        pdf_y = pdf_page_height - (rel_y * pdf_page_height)
        
        # Item size
        item_width = (item['right'] - item['left']) / flipp_width * pdf_page_width
        item_height = (item['top'] - item['bottom']) / flipp_height * pdf_page_height
        
        return {
            'x': pdf_x,
            'y': pdf_y,
            'width': item_width,
            'height': item_height
        }
    
    def overlay_badges_on_pdf(self, pdf_bytes, ai_matches, max_pages=10):
        """Overlay AI badges on PDF pages"""
        
        print(f"\n🎨 Processing PDF...")
        
        # Open PDF with PyMuPDF
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        print(f"   PDF has {len(pdf_doc)} pages")
        
        # Map items to pages
        self.map_items_to_pages()
        
        # Process each page
        enhanced_pages = []
        
        for page_num in range(1, min(len(pdf_doc) + 1, max_pages + 1)):
            
            page_data = self.items_by_page.get(page_num)
            
            if not page_data or not page_data['items']:
                # No items on this page, just render it
                page = pdf_doc[page_num - 1]
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                enhanced_pages.append(img)
                continue
            
            print(f"\n   📄 Page {page_num} ({len(page_data['items'])} items):")
            
            # Render PDF page to image
            page = pdf_doc[page_num - 1]
            pix = page.get_pixmap(dpi=150)  # 150 DPI for good quality
            page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            print(f"      Size: {page_img.width}x{page_img.height}px")
            
            # Convert to RGBA for overlay
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
                
                if score < 40:  # Only show decent deals
                    continue
                
                # Transform coordinates
                coords = self.transform_coords_to_pdf(
                    item,
                    page_data['bounds'],
                    page_img.height,
                    page_img.width
                )
                
                # Create badge
                badge_size = int(min(80, coords['width'] * 0.3))
                badge_size = max(40, badge_size)
                
                badge = self.create_ai_badge_pdf(score, ai_data['rating'], badge_size)
                
                # Position at top-right of item
                badge_x = int(coords['x'] + coords['width'] / 2 - badge_size - 5)
                badge_y = int(coords['y'] - coords['height'] / 2 + 5)
                
                # Clamp to page bounds
                badge_x = max(0, min(badge_x, page_img.width - badge_size))
                badge_y = max(0, min(badge_y, page_img.height - badge_size))
                
                # Paste badge
                overlay.paste(badge, (badge_x, badge_y), badge)
                badges_added += 1
            
            # Composite
            result = Image.alpha_composite(page_img, overlay)
            enhanced_pages.append(result.convert('RGB'))
            
            print(f"      ✅ Added {badges_added} AI badges")
        
        pdf_doc.close()
        
        return enhanced_pages
    
    def generate_overlay_pdf(self, json_file, csv_file, store_name="Safeway", max_pages=10):
        """Generate PDF with AI overlays"""
        
        print("\n" + "=" * 70)
        print(f"📄 PDF FLYER OVERLAY GENERATOR - {store_name}")
        print("=" * 70)
        
        # Load flyer data
        print(f"\n📥 Loading flyer data...")
        self.load_flyer_json(json_file)
        
        print(f"   Flyer ID: {self.flyer_id}")
        print(f"   Items: {len(self.flyer_data['items'])}")
        
        # Download PDF
        print(f"\n📥 Downloading flyer PDF...")
        pdf_bytes = self.download_flyer_pdf()
        
        if not pdf_bytes:
            print(f"\n❌ Could not download PDF")
            print(f"   Try using the reconstructed flyer generator instead")
            return None
        
        # Load AI data
        print(f"\n📊 Loading AI scores...")
        
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
            
            print(f"   Loaded {len(ai_matches)} AI scores")
        
        # Overlay badges
        enhanced_pages = self.overlay_badges_on_pdf(pdf_bytes, ai_matches, max_pages)
        
        if not enhanced_pages:
            print(f"\n❌ No pages generated")
            return None
        
        # Save as PDF
        print(f"\n💾 Saving enhanced PDF...")
        
        output_file = f"enhanced_flyer_{store_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        enhanced_pages[0].save(
            output_file,
            save_all=True,
            append_images=enhanced_pages[1:] if len(enhanced_pages) > 1 else [],
            format='PDF',
            resolution=150.0
        )
        
        print(f"\n✅ SUCCESS!")
        print(f"📄 Saved: {output_file}")
        print(f"📊 {len(enhanced_pages)} pages with AI overlays")
        print("=" * 70)
        
        return output_file


if __name__ == "__main__":
    overlay = PDFFlyerOverlay()
    
    overlay.generate_overlay_pdf(
        json_file="sobeys_flyer_data_20251223_084608.json",
        csv_file="current_flyers.csv",
        store_name="Safeway",
        max_pages=10
    )
