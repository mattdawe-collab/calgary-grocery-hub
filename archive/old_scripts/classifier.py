import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from typing import List, Literal

# Load environment variables
load_dotenv()

# 1. Define Strict Categories
CategoryType = Literal[
    "Produce", 
    "Meat & Seafood", 
    "Dairy & Eggs", 
    "Bakery", 
    "Pantry", 
    "Frozen", 
    "Beverages", 
    "Household & Personal", 
    "Snacks",
    "Other"
]

# 2. Define Data Structure
class GroceryItem(BaseModel):
    original_name: str = Field(description="The name exactly as it appeared in the flyer")
    clean_name: str = Field(description="A short, clean name for display (e.g. 'Gala Apples' instead of 'Apples Gala 3lb bag')")
    category: CategoryType
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
    
    CRITICAL INSTRUCTION:
    - Create a 'clean_name' that is human-readable for a shopping list. 
    - Remove weights, pack sizes, and redundant adjectives (e.g., convert "Coca Cola 12x355ml" to "Coca Cola").
    
    Raw Items:
    {raw_items}
    """

    # UPDATED: Using Gemini 2.5 Flash
    response = client.models.generate_content(
        model="gemini-2.5-flash", 
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": GroceryList,
        },
    )

    return response.parsed.items