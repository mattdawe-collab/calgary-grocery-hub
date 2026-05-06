"""
Calgary Grocery Hub - Product Classifier

Smart categorization that:
1. Distinguishes food from non-food items
2. Segments products by use case (snack vs meal, single vs bulk)
3. Prevents comparing incompatible items
4. Identifies brand confusion (Dove soap vs Dove chocolate)
"""

import re
import pandas as pd
from typing import Tuple, Dict

# =============================================================================
# NON-FOOD DETECTION
# =============================================================================

# Brands that are definitively NOT food
NON_FOOD_BRANDS = {
    # Personal Care
    'dove': 'personal_care',
    'irish spring': 'personal_care',
    'dial': 'personal_care',
    'olay': 'personal_care',
    'old spice': 'personal_care',
    'axe': 'personal_care',
    'degree': 'personal_care',
    'pantene': 'personal_care',
    'head & shoulders': 'personal_care',
    'garnier': 'personal_care',
    'nivea': 'personal_care',
    'aveeno': 'personal_care',
    'neutrogena': 'personal_care',
    
    # Oral Care
    'colgate': 'oral_care',
    'crest': 'oral_care',
    'oral-b': 'oral_care',
    'listerine': 'oral_care',
    'sensodyne': 'oral_care',
    
    # Laundry & Cleaning
    'tide': 'cleaning',
    'gain': 'cleaning',
    'downy': 'cleaning',
    'lysol': 'cleaning',
    'mr. clean': 'cleaning',
    'windex': 'cleaning',
    'swiffer': 'cleaning',
    'dawn': 'cleaning',
    'palmolive': 'cleaning',
    'cascade': 'cleaning',
    'clorox': 'cleaning',
    
    # Paper Products
    'bounty': 'paper',
    'charmin': 'paper',
    'cottonelle': 'paper',
    'kleenex': 'paper',
    'royale': 'paper',
    
    # Baby Care
    'huggies': 'baby',
    'pampers': 'baby',
    'enfamil': 'baby_food',
    'similac': 'baby_food',
    
    # Pet Care
    'purina': 'pet',
    'pedigree': 'pet',
    'whiskas': 'pet',
    'iams': 'pet',
    'friskies': 'pet',
}

# Keywords that indicate non-food products
NON_FOOD_KEYWORDS = [
    'shampoo', 'conditioner', 'body wash', 'soap', 'deodorant', 'antiperspirant',
    'toothpaste', 'toothbrush', 'mouthwash', 'dental', 'floss',
    'laundry', 'detergent', 'fabric softener', 'dryer sheets',
    'dish soap', 'dishwasher', 'cleaner', 'disinfectant', 'bleach',
    'paper towel', 'toilet paper', 'bathroom tissue', 'facial tissue',
    'diaper', 'wipes', 'baby wipes', 'training pants',
    'tampon', 'pad', 'panty liner', 'feminine', 'menstrual',
    'dog food', 'cat food', 'pet food', 'pet treat', 'kitty litter',
    'vitamin', 'supplement', 'medicine', 'pain relief',
    'razor', 'shaving', 'aftershave',
    'lotion', 'moisturizer', 'sunscreen', 'makeup', 'cosmetic',
]

# Brands that are ambiguous (exist in both food and non-food)
AMBIGUOUS_BRANDS = {
    'dove': {
        'food_keywords': ['chocolate', 'candy', 'bar', 'promises'],
        'nonfood_keywords': ['soap', 'body wash', 'shampoo', 'deodorant', 'lotion', 'hair'],
        'default': 'nonfood'
    },
    'bounty': {
        'food_keywords': ['chocolate', 'candy', 'coconut', 'bar'],
        'nonfood_keywords': ['paper towel', 'towels', 'rolls', 'paper'],
        'default': 'nonfood'
    },
}


def is_food_item(item_name: str, category: str = None) -> Tuple[bool, str]:
    """
    Determine if an item is a food product.
    
    Returns: (is_food: bool, reason: str)
    """
    item_lower = item_name.lower()
    
    # Check category first
    if category:
        cat_lower = str(category).lower()
        if any(x in cat_lower for x in ['household', 'personal', 'pet', 'baby', 'health']):
            if 'baby food' in item_lower or 'formula' in item_lower:
                return True, "baby_food"
            return False, f"category:{category}"
    
    # Check for ambiguous brands (using word boundary)
    for brand, rules in AMBIGUOUS_BRANDS.items():
        pattern = r'\b' + re.escape(brand) + r'\b'
        if re.search(pattern, item_lower):
            if any(kw in item_lower for kw in rules['nonfood_keywords']):
                return False, f"ambiguous_brand:{brand}->nonfood"
            if any(kw in item_lower for kw in rules['food_keywords']):
                return True, f"ambiguous_brand:{brand}->food"
            return rules['default'] == 'food', f"ambiguous_brand:{brand}->default"
    
    # Check definite non-food brands (using word boundary)
    for brand, brand_type in NON_FOOD_BRANDS.items():
        pattern = r'\b' + re.escape(brand) + r'\b'
        if re.search(pattern, item_lower):
            if brand_type == 'baby_food':
                return True, f"brand:{brand}->baby_food"
            return False, f"brand:{brand}->{brand_type}"
    
    # Check non-food keywords
    for keyword in NON_FOOD_KEYWORDS:
        if keyword in item_lower:
            return False, f"keyword:{keyword}"
    
    return True, "default:food"


# =============================================================================
# PRODUCT SIZE/TYPE SEGMENTATION
# =============================================================================

def extract_product_size(item_name: str, price: float = None) -> Dict:
    """Extract size information and classify product."""
    item_lower = item_name.lower()
    result = {
        'quantity_value': None,
        'quantity_unit': None,
        'grams_equivalent': None,
        'is_multipack': False,
        'pack_count': 1,
        'unit_price': None,
    }
    
    # Multi-pack: 12x100g, 6x650ml
    multipack = re.search(r'(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(g|ml|l|oz)\b', item_lower)
    if multipack:
        count = int(multipack.group(1))
        unit_size = float(multipack.group(2))
        unit = multipack.group(3)
        
        result['is_multipack'] = True
        result['pack_count'] = count
        result['quantity_unit'] = unit
        
        if unit == 'g':
            total_g = count * unit_size
        elif unit == 'ml':
            total_g = count * unit_size
        elif unit == 'l':
            total_g = count * unit_size * 1000
        else:
            total_g = count * unit_size * 28.35
        
        result['quantity_value'] = count * unit_size
        result['grams_equivalent'] = total_g
        
        if price and total_g:
            result['unit_price'] = price / (total_g / 1000)
        
        return result
    
    # Weight in kg
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', item_lower)
    if kg_match:
        kg = float(kg_match.group(1))
        result['quantity_value'] = kg
        result['quantity_unit'] = 'kg'
        result['grams_equivalent'] = kg * 1000
        if price:
            result['unit_price'] = price / kg
        return result
    
    # Weight in grams
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*g\b', item_lower)
    if g_match:
        grams = float(g_match.group(1))
        result['quantity_value'] = grams
        result['quantity_unit'] = 'g'
        result['grams_equivalent'] = grams
        if price:
            result['unit_price'] = price / (grams / 1000)
        return result
    
    # Volume in liters
    l_match = re.search(r'(\d+(?:\.\d+)?)\s*l\b', item_lower)
    if l_match:
        liters = float(l_match.group(1))
        result['quantity_value'] = liters
        result['quantity_unit'] = 'L'
        result['grams_equivalent'] = liters * 1000
        if price:
            result['unit_price'] = price / liters
        return result
    
    # Volume in ml
    ml_match = re.search(r'(\d+(?:\.\d+)?)\s*ml\b', item_lower)
    if ml_match:
        ml = float(ml_match.group(1))
        result['quantity_value'] = ml
        result['quantity_unit'] = 'ml'
        result['grams_equivalent'] = ml
        if price:
            result['unit_price'] = price / (ml / 1000)
        return result
    
    return result


def get_product_type(item_name: str, category: str, size_info: Dict) -> str:
    """Classify product as snack, single_serve, family, or bulk."""
    item_lower = item_name.lower()
    grams = size_info.get('grams_equivalent')
    is_multipack = size_info.get('is_multipack', False)
    
    snack_keywords = ['snack', 'mini', 'bite', 'individual', 'single', 'kids', 'drinkable']
    family_keywords = ['family', 'tub', 'value', 'bulk', 'party size']
    
    if any(kw in item_lower for kw in snack_keywords):
        return 'snack'
    if any(kw in item_lower for kw in family_keywords):
        return 'family'
    
    if is_multipack:
        per_unit = size_info.get('pack_count', 1)
        if per_unit and grams:
            per_unit_size = grams / per_unit
            if per_unit_size <= 150:
                return 'snack'
        return 'family'
    
    if grams is None:
        return 'unknown'
    
    if grams <= 200:
        return 'snack'
    elif grams <= 500:
        return 'single_serve'
    elif grams <= 1500:
        return 'family'
    else:
        return 'bulk'


def classify_product(row: pd.Series) -> Dict:
    """Comprehensive product classification."""
    item_name = row.get('Item', '')
    ai_category = row.get('ai_category')
    price = row.get('Price_Value')
    
    is_food, food_reason = is_food_item(item_name, ai_category)
    
    size_info = extract_product_size(item_name, price)
    product_type = get_product_type(item_name, str(ai_category) if ai_category else '', size_info)
    
    category = str(ai_category) if pd.notna(ai_category) and ai_category else 'Other'
    
    comparison_group = f"{category}/{product_type}"
    
    can_compare = is_food and product_type != 'unknown' and size_info.get('grams_equivalent') is not None
    
    return {
        'is_food': is_food,
        'food_reason': food_reason,
        'product_type': product_type,
        'comparison_group': comparison_group,
        'can_compare_prices': can_compare,
        'is_grocery_deal': is_food,
        'size_info': size_info,
    }


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add classification columns to a deals dataframe."""
    df['is_food'] = True
    df['food_reason'] = ''
    df['product_type'] = 'unknown'
    df['comparison_group'] = ''
    df['can_compare_prices'] = False
    df['is_grocery_deal'] = True
    
    for idx, row in df.iterrows():
        classification = classify_product(row)
        
        df.at[idx, 'is_food'] = classification['is_food']
        df.at[idx, 'food_reason'] = classification['food_reason']
        df.at[idx, 'product_type'] = classification['product_type']
        df.at[idx, 'comparison_group'] = classification['comparison_group']
        df.at[idx, 'can_compare_prices'] = classification['can_compare_prices']
        df.at[idx, 'is_grocery_deal'] = classification['is_grocery_deal']
    
    return df


def filter_grocery_deals(df: pd.DataFrame, min_score: int = 75) -> pd.DataFrame:
    """Filter to only show items that should be highlighted as grocery deals."""
    score_col = 'ai_deal_score' if 'ai_deal_score' in df.columns else 'Context_Score'
    
    if 'is_grocery_deal' not in df.columns:
        df = enrich_dataframe(df)
    
    return df[
        (df['is_grocery_deal'] == True) &
        (df[score_col] >= min_score)
    ].copy()


if __name__ == "__main__":
    # Test cases
    test_items = [
        ("Dove Bar Soap, 3x106g", 5.99),
        ("Dove Chocolate Promises, 215g", 4.99),
        ("Greek Yogurt, 650g", 5.99),
        ("Activia Yogurt, 12x100g", 7.99),
        ("Chicken Breast Boneless", 6.88),
        ("Tide Laundry Detergent, 1.86L", 14.99),
        ("Pampers Diapers, 58's", 24.99),
    ]
    
    print("=== PRODUCT CLASSIFICATION TEST ===\n")
    
    for item, price in test_items:
        row = pd.Series({
            'Item': item, 
            'Price_Value': price, 
            'ai_category': None
        })
        result = classify_product(row)
        
        print(f"Item: {item}")
        print(f"  Is Food: {result['is_food']} ({result['food_reason']})")
        print(f"  Is Grocery Deal: {result['is_grocery_deal']}")
        print(f"  Product Type: {result['product_type']}")
        print()
