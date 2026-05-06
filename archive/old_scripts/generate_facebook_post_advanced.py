"""
Advanced Facebook Post Generator
Multiple styles: Protein-focused, Budget, Premium, Family-friendly
"""

import pandas as pd
import os
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Load API key
load_dotenv()
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def analyze_deals_deeply(df):
    """Deep analysis of deals database"""
    
    print("\n🔍 DEEP DIVE ANALYSIS")
    print("=" * 70)
    
    # Overall stats
    print(f"\n📊 DATABASE OVERVIEW:")
    print(f"   Total deals: {len(df):,}")
    print(f"   Stores: {df['Store'].nunique()}")
    print(f"   Avg AI Score: {df['ai_deal_score'].mean():.1f}/100")
    
    # Category breakdown
    print(f"\n📦 BY CATEGORY:")
    if 'ai_product_category' in df.columns:
        cat_counts = df['ai_product_category'].value_counts().head(10)
        for cat, count in cat_counts.items():
            print(f"   • {cat}: {count} deals")
    
    # Protein analysis
    print(f"\n🥩 PROTEIN DEALS:")
    protein_keywords = ['meat', 'chicken', 'beef', 'pork', 'fish', 'salmon', 'turkey', 'steak', 'protein', 'eggs', 'bacon', 'ground', 'roast']
    
    protein_mask = df['Item'].str.lower().str.contains('|'.join(protein_keywords), na=False)
    protein_deals = df[protein_mask]
    
    print(f"   Found: {len(protein_deals)} protein-related deals")
    print(f"   Avg Score: {protein_deals['ai_deal_score'].mean():.1f}/100")
    
    # Top proteins
    print(f"\n⭐ TOP 10 PROTEIN DEALS:")
    top_proteins = protein_deals.nlargest(10, 'ai_deal_score')[['Item', 'Store', 'Price_Text', 'ai_deal_score']]
    for idx, row in top_proteins.iterrows():
        print(f"   {int(row['ai_deal_score'])}★ {row['Item']} - {row['Price_Text']} @ {row['Store']}")
    
    print("=" * 70)
    
    return protein_deals


def generate_post(style='protein'):
    """Generate Facebook post in different styles"""
    
    print("\n" + "=" * 70)
    print(f"📱 FACEBOOK POST GENERATOR - {style.upper()} STYLE")
    print("=" * 70)
    
    # Load data
    if not os.path.exists('current_flyers.csv'):
        print("❌ current_flyers.csv not found!")
        return
    
    df = pd.read_csv('current_flyers.csv')
    df = df[df['ai_deal_score'] > 0]
    
    # Deep analysis
    protein_deals = analyze_deals_deeply(df)
    
    # Style-specific prompts
    prompts = {
        'protein': f"""You are a fitness-focused grocery expert writing for Calgary gym-goers and health enthusiasts.

MISSION: Create a PROTEIN-OBSESSED Facebook post highlighting this week's BEST protein deals.

ANALYZE DEEPLY:
1. Which proteins have the BEST $/gram protein value?
2. Which stores have the BEST meat prices this week?
3. Any RARE deals on premium proteins (salmon, steak, organic)?
4. Compare chicken, beef, pork, fish prices across stores
5. Highlight any protein items scoring 80+ on AI quality

TOP PROTEIN DEALS TO ANALYZE:
{chr(10).join([f"• {row['Item']} - {row['Price_Text']} at {row['Store']} (Score: {int(row['ai_deal_score'])})" 
               for _, row in protein_deals.nlargest(20, 'ai_deal_score').iterrows()])}

FACEBOOK POST STRUCTURE:
🥩 Catchy protein-focused headline
💪 Brief intro (why protein matters)
🎯 5-8 SPECIFIC protein deals:
   - Item + price + store
   - Why it's a great deal
   - Protein content if known
🏆 "Best overall protein buy"
💡 Pro tip for meal prep
📍 Call to action

TONE: Enthusiastic fitness buddy sharing deals
LENGTH: 250-300 words
DATE: {datetime.now().strftime('%B %d, %Y')}""",

        'budget': f"""You are a budget-savvy grocery expert helping Calgary families save money.

MISSION: Create a Facebook post highlighting the MOST COST-EFFECTIVE protein sources this week.

ANALYZE:
1. Cheapest protein per pound/kg
2. Multi-buy deals on proteins
3. Budget cuts (ground beef, chicken thighs, etc)
4. Family pack deals
5. Compare "cheap but good" options across stores

TOP VALUE DEALS:
{chr(10).join([f"• {row['Item']} - {row['Price_Text']} at {row['Store']} (Score: {int(row['ai_deal_score'])})" 
               for _, row in df.nlargest(30, 'ai_deal_score').iterrows()])}

POST STRUCTURE:
💰 Money-saving headline
👨‍👩‍👧 Family budget intro
🛒 8-10 BEST value deals (mix of proteins and staples)
💡 Budget stretching tips
📊 This week vs last week savings
✅ Call to action

TONE: Helpful money-saving friend
LENGTH: 300 words max
DATE: {datetime.now().strftime('%B %d, %Y')}""",

        'premium': f"""You are a foodie expert writing for Calgary home chefs who want quality ingredients.

MISSION: Highlight PREMIUM protein deals - the good stuff at great prices.

ANALYZE:
1. Premium cuts on sale (ribeye, filet, wild salmon)
2. Organic/grass-fed proteins
3. Specialty meats (lamb, veal, duck)
4. High-end seafood deals
5. Artisanal/boutique proteins

PREMIUM DEALS:
{chr(10).join([f"• {row['Item']} - {row['Price_Text']} at {row['Store']} (Score: {int(row['ai_deal_score'])})" 
               for _, row in df[df['Item'].str.contains('organic|grass|prime|angus|wild|AAA|sterling', case=False, na=False)]
               .nlargest(20, 'ai_deal_score').iterrows()])}

POST STRUCTURE:
✨ Gourmet-focused headline
🍴 Quality matters intro
🥩 5-7 PREMIUM protein deals
👨‍🍳 Cooking suggestions
🏆 "Deal of the week" feature
📍 Where to find

TONE: Sophisticated but accessible
LENGTH: 250 words
DATE: {datetime.now().strftime('%B %d, %Y')}"""
    }
    
    prompt = prompts.get(style, prompts['protein'])
    
    print("\n🤖 Generating post with Gemini 3 Pro (state-of-the-art reasoning)...")
    print("   ⏳ Using Google's most advanced model for comprehensive analysis...")
    
    # Call Gemini 3 Pro - State-of-the-art reasoning model (November 2025)
    model = genai.GenerativeModel('gemini-3-pro-preview-11-2025')
    
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.85,
            top_p=0.95,
            max_output_tokens=2500,  # More space for thorough analysis
        )
    )
    
    post = response.text
    
    # Display
    print("\n" + "=" * 70)
    print(f"📱 {style.upper()} FACEBOOK POST - READY!")
    print("=" * 70)
    print()
    print(post)
    print()
    print("=" * 70)
    
    # Save
    output_file = f"facebook_post_{style}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"STYLE: {style.upper()}\n")
        f.write(f"GENERATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")
        f.write(post)
    
    print(f"\n💾 Saved to: {output_file}")
    
    return post


if __name__ == "__main__":
    import sys
    
    print("\n📱 FACEBOOK POST GENERATOR")
    print("=" * 70)
    print("\nAvailable styles:")
    print("  1. protein  - Focus on protein deals (gym/health)")
    print("  2. budget   - Budget-friendly family deals")
    print("  3. premium  - Premium/gourmet protein deals")
    print()
    
    if len(sys.argv) > 1:
        style = sys.argv[1]
    else:
        style = input("Select style (protein/budget/premium) [protein]: ").strip().lower() or 'protein'
    
    if style not in ['protein', 'budget', 'premium']:
        print(f"⚠️  Unknown style '{style}', using 'protein'")
        style = 'protein'
    
    generate_post(style)
