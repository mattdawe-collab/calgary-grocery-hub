"""
Real Flyer Overlay System - Production Version
Downloads actual flyer pages and overlays AI badges at correct positions
Uses Flipp's coordinate system to place badges accurately
"""

import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import json
import os
from datetime import datetime

class RealFlyerOverlay:
    """Overlay AI badges on real flyer pages"""
    
    def __init__(self):
        self.flyer_id = None
        self.flyer_data = None
        self.items_by_page = {}
    
    def load_flyer_json(self, json_file):
        """Load flyer data from JSON"""
        with open(json_file, 'r') as f:
            self.flyer_data = json.load(f)
        
        # Extract flyer ID from first item
        if self.flyer_data['items']:
            self.flyer_id = self.flyer_data['items'][0]['flyer_id']
    
    def map_items_to_pages(self):
        """Map each item to its page using coordinates"""
        pages = self.flyer_data['pages']
        items = self.flyer_data['items']
        
        # Initialize
        for page in pages:
            self.items_by_page[page['page']] = {
                'bounds': page,
                'items': []
            }
        
        # Assign items to pages
        for item in items:
            item_center_x = (item['left'] + item['right']) / 2
            item_center_y = (item['top'] + item['bottom']) / 2
            
            # Find which page contains this item
            for page in pages:
                if (page['left'] <= item_center_x <= page['right'] and
                    page['bottom'] <= item_center_y <= page['top']):
                    
                    self.items_by_page[page['page']]['items'].append(item)
                    break
    
    def get_page_image_url(self, page_num):
        """Construct page image URL"""
        # Flipp page images follow this pattern
        # Try different possible URL structures
        possible_urls = [
            f"https://da.flippcdn.com/flyer-images/{self.flyer_id}/original/{page_num}.jpg",
            f"https://da.flippcdn.com/flyer-images/{self.flyer_id}/large/{page_num}.jpg",
            f"https://flipp-flyerkit-production.s3.amazonaws.com/flyers/{self.flyer_id}/pages/{page_num}.jpg",
        ]
        
        return possible_urls
    
    def download_page_image(self, page_num):
        """Download flyer page image"""
        urls = self.get_page_image_url(page_num)
        
        for url in urls:
            try:
                print(f"      Trying: {url[:60]}...")
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print(f"      ✅ Downloaded!")
                    return Image.open(BytesIO(response.content))
            except Exception as e:
                continue
        
        print(f"      ❌ Could not download page image")
        return None
    
    def create_ai_badge(self, score, rating, size=120):
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
        draw.ellipse([6, 6, size-1, size-1], fill=(0, 0, 0, 100))
        
        # Circle
        draw.ellipse([0, 0, size-7, size-7], fill=color, outline=(255, 255, 255), width=6)
        
        # Score text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.35))
        except:
            font = ImageFont.load_default()
        
        score_text = str(score)
        bbox = draw.textbbox((0, 0), score_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        text_x = (size - text_width) // 2 - 3
        text_y = (size - text_height) // 2 - 5
        
        draw.text((text_x, text_y), score_text, fill=(255, 255, 255), font=font)
        
        return badge
    
    def transform_coordinates(self, item_coords, page_bounds, page_image_size):
        """Transform Flipp coordinates to image pixel coordinates"""
        
        # Flipp coordinate system bounds
        flipp_left = page_bounds['left']
        flipp_right = page_bounds['right']
        flipp_top = page_bounds['top']
        flipp_bottom = page_bounds['bottom']
        
        flipp_width = flipp_right - flipp_left
        flipp_height = flipp_top - flipp_bottom
        
        # Item coordinates
        item_left = item_coords['left']
        item_right = item_coords['right']
        item_top = item_coords['top']
        item_bottom = item_coords['bottom']
        
        # Calculate relative positions (0 to 1)
        rel_x = (((item_left + item_right) / 2) - flipp_left) / flipp_width
        rel_y = (flipp_top - ((item_top + item_bottom) / 2)) / flipp_height
        
        # Convert to pixel coordinates
        img_width, img_height = page_image_size
        
        pixel_x = int(rel_x * img_width)
        pixel_y = int(rel_y * img_height)
        
        # Calculate item size in pixels
        item_width_rel = (item_right - item_left) / flipp_width
        item_height_rel = (item_top - item_bottom) / flipp_height
        
        item_pixel_width = int(item_width_rel * img_width)
        item_pixel_height = int(item_height_rel * img_height)
        
        return {
            'center_x': pixel_x,
            'center_y': pixel_y,
            'width': item_pixel_width,
            'height': item_pixel_height
        }
    
    def overlay_badges_on_page(self, page_image, page_num, ai_matches):
        """Overlay AI badges on a page"""
        
        page_data = self.items_by_page.get(page_num)
        
        if not page_data or not page_data['items']:
            return page_image
        
        # Convert to RGBA
        if page_image.mode != 'RGBA':
            page_image = page_image.convert('RGBA')
        
        # Create overlay layer
        overlay = Image.new('RGBA', page_image.size, (0, 0, 0, 0))
        
        badges_added = 0
        
        for item in page_data['items']:
            item_name = item['name']
            
            # Find AI match
            if item_name not in ai_matches:
                continue
            
            ai_data = ai_matches[item_name]
            score = ai_data['score']
            rating = ai_data['rating']
            
            # Skip low scores
            if score < 40:
                continue
            
            # Transform coordinates
            pixel_coords = self.transform_coordinates(
                item,
                page_data['bounds'],
                page_image.size
            )
            
            # Create badge
            badge_size = min(100, pixel_coords['width'] // 2, pixel_coords['height'] // 3)
            badge_size = max(60, badge_size)  # Minimum 60px
            
            badge = self.create_ai_badge(score, rating, badge_size)
            
            # Position badge at top-right of item
            badge_x = pixel_coords['center_x'] + pixel_coords['width'] // 2 - badge_size
            badge_y = pixel_coords['center_y'] - pixel_coords['height'] // 2
            
            # Clamp to image bounds
            badge_x = max(0, min(badge_x, page_image.width - badge_size))
            badge_y = max(0, min(badge_y, page_image.height - badge_size))
            
            # Paste badge
            overlay.paste(badge, (badge_x, badge_y), badge)
            badges_added += 1
        
        # Composite
        result = Image.alpha_composite(page_image, overlay)
        
        print(f"      ✅ Added {badges_added} AI badges")
        
        return result.convert('RGB')
    
    def generate_overlay_flyer(self, json_file, csv_file, store_name="Safeway", max_pages=5):
        """Generate real flyer with AI overlays"""
        
        print("\n" + "=" * 70)
        print(f"🎨 REAL FLYER OVERLAY GENERATOR - {store_name}")
        print("=" * 70)
        
        # Load flyer data
        print(f"\n📥 Loading flyer JSON...")
        self.load_flyer_json(json_file)
        print(f"   Flyer ID: {self.flyer_id}")
        print(f"   Pages: {len(self.flyer_data['pages'])}")
        print(f"   Items: {len(self.flyer_data['items'])}")
        
        # Map items to pages
        print(f"\n🗺️  Mapping items to pages...")
        self.map_items_to_pages()
        
        items_per_page = [(p, len(self.items_by_page[p]['items'])) 
                          for p in sorted(self.items_by_page.keys())]
        
        for page_num, count in items_per_page[:10]:
            print(f"   Page {page_num}: {count} items")
        
        # Load AI scores
        print(f"\n📊 Loading AI scores...")
        
        if not os.path.exists(csv_file):
            print(f"   ⚠️  {csv_file} not found")
            return None
        
        df = pd.read_csv(csv_file)
        df = df[df['Store'].str.contains(store_name, case=False, na=False)]
        
        print(f"   Loaded {len(df)} AI-scored items")
        
        # Create name→AI data mapping
        ai_matches = {}
        
        for _, row in df.iterrows():
            if pd.notna(row.get('ai_deal_score')) and row['ai_deal_score'] > 0:
                ai_matches[row['Item']] = {
                    'score': int(row['ai_deal_score']),
                    'rating': row.get('ai_deal_rating', 'not_a_deal')
                }
        
        print(f"   Matched {len(ai_matches)} items with scores")
        
        # Process pages
        print(f"\n🎨 Processing pages...")
        
        enhanced_pages = []
        
        # Get pages with most items
        best_pages = sorted(items_per_page, key=lambda x: x[1], reverse=True)[:max_pages]
        
        for page_num, item_count in best_pages:
            print(f"\n   📄 Page {page_num} ({item_count} items):")
            
            # Download page
            page_img = self.download_page_image(page_num)
            
            if page_img:
                print(f"      Size: {page_img.width}x{page_img.height}px")
                
                # Overlay badges
                enhanced_page = self.overlay_badges_on_page(page_img, page_num, ai_matches)
                
                enhanced_pages.append((page_num, enhanced_page))
            else:
                print(f"      ⚠️  Could not download page image")
        
        if not enhanced_pages:
            print(f"\n❌ No pages could be enhanced")
            print(f"   Page image URLs may have changed")
            return None
        
        # Save as PDF
        print(f"\n💾 Saving enhanced flyer...")
        
        output_file = f"enhanced_flyer_{store_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        # Sort by page number
        enhanced_pages.sort(key=lambda x: x[0])
        
        images = [img for _, img in enhanced_pages]
        
        images[0].save(
            output_file,
            save_all=True,
            append_images=images[1:] if len(images) > 1 else [],
            format='PDF',
            resolution=300.0
        )
        
        print(f"\n✅ SUCCESS!")
        print(f"📄 Saved: {output_file}")
        print(f"📊 {len(images)} pages with AI overlays")
        print("=" * 70)
        
        return output_file


if __name__ == "__main__":
    overlay = RealFlyerOverlay()
    
    overlay.generate_overlay_flyer(
        json_file="sobeys_flyer_data_20251223_084608.json",
        csv_file="current_flyers.csv",
        store_name="Safeway",
        max_pages=5
    )
