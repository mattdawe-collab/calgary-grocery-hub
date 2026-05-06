import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# --- CONFIGURATION ---
# We have hardcoded your credentials here as requested.
# PLEASE CHANGE YOUR DATABASE PASSWORD IN SUPABASE AFTER THIS WORKS.
DB_CONNECTION_STRING = "postgresql://postgres.pjkbxjrsbjwqkzogdcwh:ddR3wwyFIB4VynWy@aws-1-ca-central-1.pooler.supabase.com:5432/postgres"

CSV_FILE = 'seton_grocery_history.csv'

def migrate_data():
    print(f"--- MIGRATION START ---")
    print(f"Target: Supabase Canada (Port 5432)")
    
    # 1. LOAD CSV
    try:
        df = pd.read_csv(CSV_FILE)
        print(f"Loaded {len(df)} rows.")
    except FileNotFoundError:
        print(f"Error: Could not find '{CSV_FILE}'")
        return

    # 2. PREPARE
    if 'recorded_at' not in df.columns:
        df['recorded_at'] = datetime.now()
    
    # Map your CSV headers to the Database columns
    df = df.rename(columns={'Item': 'product_name', 'Price_Value': 'price'})
    
    try:
        db_ready_df = df[['product_name', 'price', 'recorded_at']]
    except KeyError as e:
        print(f"Column Error: {e}")
        return

    # 3. UPLOAD
    print("Connecting...")
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        
        # Test connection
        with engine.connect() as conn:
            print("Connected! Uploading data...")
            db_ready_df.to_sql('scanned_prices', engine, if_exists='append', index=False)
            print("\n✅ SUCCESS! Your data is in the cloud.")
            
    except Exception as e:
        print("\n❌ FAILED")
        print(f"Error: {e}")

if __name__ == "__main__":
    migrate_data()