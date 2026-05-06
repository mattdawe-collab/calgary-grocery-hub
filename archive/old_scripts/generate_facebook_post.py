"""
Facebook Post Generator - Protein-Focused Deal Hunter
Analyzes the database and creates engaging social media posts
"""

import pandas as pd
import os
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Load API key
load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def generate_facebook_post():
    """Generate an engaging Facebook post about this week's best protein deals"""
    
    print("=" * 70)
    print("📱 FACEBOOK POST GENERATOR - PROTEIN DEALS")
    print("=" * 70)
    
    # Load data
    if not os.path.exists('current_flyers.csv'):
        print("❌ current_flyers.csv not found!")
        return
    
    df = pd.read_csv('current_flyers.csv')
    
    print(f"\n📊 Analyzing {len(df):,} deals...")
    
    # Filter for items with AI scores
    df = df[df['ai_deal_score'] > 0]
    
    # Get top deals
    top_deals = df.nlargest(50, 'ai_deal_score')
    
    # Prepare data summary for AI
    deals_summary = []
    
    for _, row in top_deals.iterrows():
        deals_summary.append({
            'item': row['Item'],
            'store': row['Store'],
            'price': row['Price_Text'],
            'score': int(row['ai_deal_score']),
            'rating': row.get('ai_deal_rating', 'good'),
            'category': row.get('ai_product_category', 'Unknown'),
            'brand': row.get('ai_brand', 'Unknown'),
            'savings_reason': row.get('ai_deal_reasoning', '')
        })
    
    # Create comprehensive prompt
    prompt = f"""You are a grocery deal expert writing a Facebook post for Calgary shoppers.

TASK: Analyze this week's grocery deals and create an ENGAGING Facebook post with a STRONG BIAS toward PROTEIN items (meat, poultry, fish, eggs, dairy proteins).

DATABASE: {len(deals_summary)} top-scoring deals from this week's flyers

YOUR ANALYSIS REQUIREMENTS:
1. DEEP DIVE into the data - look at scores, prices, brands, categories
2. PRIORITIZE protein deals - meat, chicken, fish, eggs, protein-rich items
3. IDENTIFY the absolute BEST protein deals this week
4. COMPARE prices across stores for the same proteins
5. HIGHLIGHT any exceptional or rare protein deals
6. MENTION 5-8 specific deals with prices and stores
7. Include a mix: premium proteins AND budget-friendly options

DEALS DATA:
{chr(10).join([f"• {d['item']} - {d['price']} at {d['store']} (Score: {d['score']}/100, {d['category']})" for d in deals_summary])}

FACEBOOK POST REQUIREMENTS:
✅ Attention-grabbing headline with emojis
✅ Focus on PROTEIN deals first (meat, chicken, fish, eggs)
✅ List 5-8 specific deals with:
   - Item name
   - Price
   - Store name
   - Why it's a great deal
✅ Include both premium cuts AND budget options
✅ Add a "Pro Tip" or "Don't Miss" section
✅ End with call-to-action
✅ Use emojis strategically (🥩🍗🐟🥚 etc)
✅ Keep it under 300 words
✅ Sound excited but authentic
✅ Mention today's date: {datetime.now().strftime('%B %d, %Y')}

TONE: Friendly, enthusiastic, helpful (like texting a friend about deals)

FORMAT: Ready-to-paste Facebook post with line breaks and emojis

Now write the post:"""

    print("\n🤖 Generating Facebook post with Gemini 3 Pro...")
    print("   (Deep analysis in progress...)\n")
    
    # Call Gemini 3 Pro - Most advanced model currently available
    model = genai.GenerativeModel('gemini-3-pro-preview-11-2025')
    
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.8,  # More creative
            top_p=0.95,
            max_output_tokens=2000,
        )
    )
    
    post = response.text
    
    # Display the post
    print("=" * 70)
    print("📱 FACEBOOK POST - READY TO SHARE!")
    print("=" * 70)
    print()
    print(post)
    print()
    print("=" * 70)
    
    # Save to file
    output_file = f"facebook_post_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(post)
    
    print(f"\n💾 Saved to: {output_file}")
    print("📋 Copy and paste to Facebook!")
    
    return post


if __name__ == "__main__":
    generate_facebook_post()
