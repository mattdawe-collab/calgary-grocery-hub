import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from typing import List, Literal, Optional

# Load environment variables
load_dotenv()

# 1. Define Strict Categories (Main Categories)
CategoryType = Literal[
    "Produce",
    "Beef",
    "Pork", 
    "Poultry",
    "Lamb",
    "Seafood",
    "Dairy & Eggs", 
    "Bakery", 
    "Pantry", 
    "Frozen", 
    "Beverages", 
    "Household & Personal", 
    "Snacks",
    "Other"
]

# Beef Subcategories
BeefSubCategory = Literal[
    "Steaks",
    "Roasts",
    "Extra Lean Ground Beef",
    "Lean Ground Beef",
    "Regular Ground Beef",
    "Stewing Beef",
    "Striploin",
    "Sirloin",
    "Rib Eye",
    "T-Bone",
    "Brisket",
    "Short Ribs",
    "Other Beef"
]

# Poultry Subcategories
PoultrySubCategory = Literal[
    "Boneless Chicken Breast",
    "Bone-In Chicken Breast",
    "Boneless Chicken Thighs",
    "Bone-In Chicken Thighs",
    "Chicken Drumsticks",
    "Chicken Wings",
    "Whole Chicken",
    "Ground Chicken",
    "Ground Turkey",
    "Whole Turkey",
    "Turkey Breast",
    "Other Poultry"
]

# Pork Subcategories
PorkSubCategory = Literal[
    "Pork Chops",
    "Pork Tenderloin",
    "Pork Roast",
    "Pork Ribs",
    "Ground Pork",
    "Pork Shoulder",
    "Bacon",
    "Ham",
    "Sausages",
    "Other Pork"
]

# Lamb Subcategories
LambSubCategory = Literal[
    "Lamb Chops",
    "Lamb Roast",
    "Ground Lamb",
    "Lamb Shanks",
    "Other Lamb"
]

# Seafood Subcategories
SeafoodSubCategory = Literal[
    "Salmon",
    "Shrimp",
    "Cod",
    "Tilapia",
    "Tuna",
    "Scallops",
    "Crab",
    "Lobster",
    "Other Seafood"
]

# Produce Subcategories
ProduceSubCategory = Literal[
    "Apples",
    "Bananas",
    "Berries",
    "Citrus",
    "Tropical Fruit",
    "Stone Fruit",
    "Leafy Greens",
    "Root Vegetables",
    "Peppers",
    "Tomatoes",
    "Onions & Garlic",
    "Potatoes",
    "Other Produce"
]

# Helper to get valid subcategories for a category
def get_subcategories_for_category(category: str):
    """Returns the subcategory literal list for a given category"""
    subcategory_map = {
        "Beef": ["Steaks", "Roasts", "Extra Lean Ground Beef", "Lean Ground Beef", "Regular Ground Beef", 
                 "Stewing Beef", "Striploin", "Sirloin", "Rib Eye", "T-Bone", "Brisket", "Short Ribs", "Other Beef"],
        "Poultry": ["Boneless Chicken Breast", "Bone-In Chicken Breast", "Boneless Chicken Thighs", 
                    "Bone-In Chicken Thighs", "Chicken Drumsticks", "Chicken Wings", "Whole Chicken", 
                    "Ground Chicken", "Ground Turkey", "Whole Turkey", "Turkey Breast", "Other Poultry"],
        "Pork": ["Pork Chops", "Pork Tenderloin", "Pork Roast", "Pork Ribs", "Ground Pork", 
                 "Pork Shoulder", "Bacon", "Ham", "Sausages", "Other Pork"],
        "Lamb": ["Lamb Chops", "Lamb Roast", "Ground Lamb", "Lamb Shanks", "Other Lamb"],
        "Seafood": ["Salmon", "Shrimp", "Cod", "Tilapia", "Tuna", "Scallops", "Crab", "Lobster", "Other Seafood"],
        "Produce": ["Apples", "Bananas", "Berries", "Citrus", "Tropical Fruit", "Stone Fruit", 
                    "Leafy Greens", "Root Vegetables", "Peppers", "Tomatoes", "Onions & Garlic", 
                    "Potatoes", "Other Produce"]
    }
    return subcategory_map.get(category, ["N/A"])

# 2. Define Data Structure
class GroceryItem(BaseModel):
    original_name: str = Field(description="The name exactly as it appeared in the flyer")
    clean_name: str = Field(description="A short, clean name for display (e.g. 'Gala Apples' instead of 'Apples Gala 3lb bag')")
    category: CategoryType
    sub_category: Optional[str] = Field(description="Subcategory if applicable (e.g., 'Boneless Chicken Breast' for Poultry, 'Lean Ground Beef' for Beef)", default=None)
    is_deal: bool = Field(description="True if this looks like a significant sale/doorcrasher")

class GroceryList(BaseModel):
    items: List[GroceryItem]

# 3. Main Classification Function
def categorize_groceries(raw_items: List[str]):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
    You are a grocery data assistant. 
    Analyze the following list of raw flyer items and categorize them strictly.
    
    CATEGORIES:
    - Produce (sub: Apples, Bananas, Berries, Citrus, Leafy Greens, Root Vegetables, etc.)
    - Beef (sub: Steaks, Roasts, Extra Lean Ground Beef, Lean Ground Beef, Regular Ground Beef, Stewing Beef, Striploin, Sirloin, Rib Eye, etc.)
    - Poultry (sub: Boneless Chicken Breast, Bone-In Chicken Breast, Boneless Chicken Thighs, Bone-In Chicken Thighs, Chicken Wings, Whole Chicken, Ground Turkey, etc.)
    - Pork (sub: Pork Chops, Pork Tenderloin, Pork Roast, Pork Ribs, Ground Pork, Bacon, Ham, Sausages, etc.)
    - Lamb (sub: Lamb Chops, Lamb Roast, Ground Lamb, Lamb Shanks, etc.)
    - Seafood (sub: Salmon, Shrimp, Cod, Tilapia, Tuna, Scallops, Crab, Lobster, etc.)
    - Dairy & Eggs
    - Bakery
    - Pantry
    - Frozen
    - Beverages
    - Household & Personal
    - Snacks
    - Other
    
    CRITICAL INSTRUCTIONS:
    - Create a 'clean_name' that is human-readable for a shopping list
    - Remove weights, pack sizes, and redundant adjectives (e.g., convert "Coca Cola 12x355ml" to "Coca Cola")
    - For meat items (Beef, Pork, Poultry, Lamb, Seafood), ALWAYS provide a sub_category
    - For produce, provide a sub_category when possible
    - Be specific with meat subcategories: distinguish between boneless/bone-in, ground beef leanness (extra lean/lean/regular), cut types
    
    Raw Items:
    {raw_items}
    """

    # Using Gemini 2.5 Flash - Better reasoning for accurate categorization
    response = client.models.generate_content(
        model="gemini-2.5-flash", 
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": GroceryList,
        },
    )

    return response.parsed.items
