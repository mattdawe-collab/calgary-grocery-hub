import streamlit as st
import numpy as np
import pandas as pd
from PIL import Image
from pyzbar.pyzbar import decode
import requests
import google.generativeai as genai
import os
from dotenv import load_dotenv
import json
from supabase import create_client, Client
from thefuzz import process, fuzz

# --- 1. CONFIGURATION (EDIT THIS TO MATCH YOUR DB) ---
# Check your Supabase Table Editor for the exact name!
TABLE_NAME = "price_reports"  # <--- CHANGE THIS if your table is named 'deal_scans' or 'grocery_deals'

st.set_page_config(page_title="Waze for Groceries (Alpha)", page_icon="🛒", layout="centered")

# --- 2. CONNECTIONS ---
load_dotenv()

# Gemini Setup
api_key = os.getenv("GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.0-flash-exp'
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("❌ Gemini API Key missing. Check .env")

# Supabase Setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase Keys Missing! Check your .env file.")
    st.stop()

# Initialize Connection
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 3. CLOUD DATA FUNCTIONS ---

@st.cache_data(ttl=10) # Refresh data every 10 seconds
def fetch_live_history():
    """Pulls the latest verified price reports from Supabase."""
    try:
        # Fetch all records from the configured table
        response = supabase.table(TABLE_NAME).select("*").execute()
        df = pd.DataFrame(response.data)
        
        if df.empty:
            return pd.DataFrame()

        # Convert types for math if columns exist
        if 'reported_at' in df.columns:
            df['reported_at'] = pd.to_datetime(df['reported_at'])
        
        # Handle price column (might be 'price' or 'numeric_price' depending on your setup)
        if 'price' in df.columns:
            df['numeric_price'] = pd.to_numeric(df['price'])
        
        return df
    except Exception as e:
        st.error(f"Cloud Error (Check your Table Name!): {e}")
        return pd.DataFrame()

def report_price_to_cloud(name, price, store):
    """The 'Waze' Report Button: Pushes a new price to Supabase."""
    data = {
        "product_name": name,
        "price": price,
        "store_name": store
        # Note: If your DB expects 'filename' or 'file_path', we might need to adjust this payload
    }
    try:
        supabase.table(TABLE_NAME).insert(data).execute()
        st.toast("Price Reported to Cloud! ☁️", icon="🚀")
        st.cache_data.clear() # Clear cache so the new price shows up instantly
        return True
    except Exception as e:
        st.error(f"Upload Failed: {e}")
        return False

# --- 4. AI INTELLIGENCE ---

def fetch_product_name_api(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        r = requests.get(url, timeout=2).json()
        if r.get("status") == 1: return r.get("product", {}).get("product_name")
    except: pass
    return None

def identify_image_with_gemini(image):
    if not api_key: return None
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = "Identify Brand, Generic Type, and Size. Ex: 'Kraft Dinner 200g'. Return ONLY text."
    try:
        return model.generate_content([prompt, image]).text.strip()
    except: return None

def standardize_name(raw_name):
    if not raw_name: return None
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = f"Clean this grocery name: '{raw_name}'. Format: 'Brand Product Size'. Example: 'Catelli Pasta 500g'. Return ONLY text."
    try:
        return model.generate_content(prompt).text.strip()
    except: return raw_name

# --- 5. UI & MAIN LOGIC ---
st.title("🛒 Waze for Groceries")

# Load Cloud Data
df = fetch_live_history()

# Show recent activity (The "Feed")
with st.expander("🌍 Live Community Feed", expanded=False):
    if not df.empty:
        # Try to show relevant columns, falling back if they don't exist
        cols_to_show = [c for c in ['product_name', 'price', 'store_name', 'reported_at'] if c in df.columns]
        if cols_to_show:
            st.dataframe(df[cols_to_show].sort_values('reported_at', ascending=False).head(5))
        else:
            st.write(df.head())
    else:
        st.info("No reports yet. Be the first!")

if 'scan_result' not in st.session_state:
    st.session_state.scan_result = None

# CAMERA INPUT
img_buffer = st.camera_input("Scan Item", label_visibility="collapsed")

if img_buffer:
    image_pil = Image.open(img_buffer)
    img_array = np.array(image_pil)
    
    raw_name = None
    
    # 1. Barcode
    decoded = decode(img_array)
    if decoded:
        raw_name = fetch_product_name_api(decoded[0].data.decode("utf-8"))
        
    # 2. Vision (Backup)
    if not raw_name:
        with st.spinner("AI analyzing packaging..."):
            raw_name = identify_image_with_gemini(image_pil)

    # 3. Process
    if raw_name:
        clean_name = standardize_name(raw_name)
        st.session_state.scan_result = clean_name
        st.toast(f"Scanned: {clean_name}", icon="✅")

# RESULT CARD
if st.session_state.scan_result:
    item_name = st.session_state.scan_result
    st.divider()
    st.header(item_name)
    
    # Search Cloud History for matches
    history_matches = pd.DataFrame()
    if not df.empty and 'product_name' in df.columns:
        choices = df['product_name'].unique()
        best_match = process.extractOne(item_name, choices, scorer=fuzz.token_set_ratio)
        
        if best_match and best_match[1] > 60: # If >60% match confidence
            matched_name = best_match[0]
            history_matches = df[df['product_name'] == matched_name]
    
    # Display Data
    if not history_matches.empty:
        min_price = history_matches['numeric_price'].min()
        avg_price = history_matches['numeric_price'].mean()
        
        c1, c2 = st.columns(2)
        c1.metric("Best Price Seen", f"${min_price:.2f}")
        c2.metric("Average Price", f"${avg_price:.2f}")
        
        if 'reported_at' in history_matches.columns:
            st.line_chart(history_matches.set_index('reported_at')['numeric_price'])
    else:
        st.info("🆕 New Item! No history found.")

    # REPORTING FORM
    with st.container(border=True):
        st.subheader("📝 Report Price")
        with st.form("report"):
            p_price = st.number_input("Price ($)", min_value=0.01, step=0.01)
            p_store = st.selectbox("Store", ["Safeway Seton", "Superstore Seton", "Save-On Seton", "Co-op Auburn Bay"])
            
            if st.form_submit_button("📢 Broadcast Deal"):
                report_price_to_cloud(item_name, p_price, p_store)
                st.session_state.scan_result = None # Reset
                st.rerun()

    if st.button("Cancel Scan"):
        st.session_state.scan_result = None
        st.rerun()