from fastapi import FastAPI, HTTPException
import pandas as pd
from typing import List, Optional

app = FastAPI()

# 1. LOAD YOUR DATA
# We load the CSV once when the server starts
csv_file = "seton_grocery_history.csv" 

try:
    # Load data and fill missing values to avoid errors
    df = pd.read_csv(csv_file)
    df = df.fillna("")
    print(f"✅ Loaded {len(df)} records from {csv_file}")
except Exception as e:
    print(f"❌ Error loading CSV: {e}")
    df = pd.DataFrame() # Create empty if fails

@app.get("/")
def home():
    return {"message": "Weekly Deals API is Online", "record_count": len(df)}

# 2. SEARCH ENDPOINT (The Core Feature)
# Usage: /search?q=ketchup
@app.get("/search")
def search_items(q: str):
    """
    Search for a product by name (e.g., 'milk', 'bread').
    Returns all historical prices for that item.
    """
    if df.empty:
        return {"error": "No data loaded"}

    # Case-insensitive search
    # We look in 'Item' and 'Original_Name' columns
    mask = (
        df['Item'].str.contains(q, case=False, na=False) | 
        df['Original_Name'].str.contains(q, case=False, na=False)
    )
    results = df[mask]

    # Convert to a list of dictionaries (JSON)
    return {
        "query": q,
        "count": len(results),
        "results": results.to_dict(orient="records")
    }

# 3. STATS ENDPOINT (Optional)
# Usage: /stats
@app.get("/stats")
def get_stats():
    return {
        "total_records": len(df),
        "stores": df['Store'].unique().tolist(),
        "categories": df['Category'].unique().tolist()
    }