"""
COMPREHENSIVE AI ANALYZER DIAGNOSTIC
Shows EXACTLY what's failing with full error details
"""
import os
import sys
import traceback

print("="*80)
print("COMPREHENSIVE AI ANALYZER DIAGNOSTIC")
print("="*80)
print()

# Step 1: Check Python version
print("[STEP 1] Python Version Check")
print("-"*80)
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")
print()

# Step 2: Check for .env file
print("[STEP 2] Checking .env File")
print("-"*80)
env_path = ".env"
try:
    if os.path.exists(env_path):
        print(f"✅ .env file exists")
        # Try to load it
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print(f"✅ dotenv loaded successfully")
        except ImportError:
            print(f"⚠️  python-dotenv not installed, but .env exists")
    else:
        print(f"❌ .env file NOT found")
        print(f"   Create it with: GEMINI_API_KEY=your_key_here")
except Exception as e:
    print(f"⚠️  Error checking .env: {e}")
print()

# Step 3: Check API Key
print("[STEP 3] Checking API Key")
print("-"*80)
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if api_key:
    print(f"✅ API Key found")
    print(f"   Key starts with: {api_key[:15]}...")
    print(f"   Key ends with: ...{api_key[-4:]}")
    print(f"   Key length: {len(api_key)} characters")
else:
    print(f"❌ NO API KEY FOUND")
    print(f"   Checked: GEMINI_API_KEY")
    print(f"   Checked: GOOGLE_API_KEY")
    print(f"   Fix: Add to .env file or set environment variable")
    print()
    print(f"STOPPING - Cannot proceed without API key")
    exit(1)
print()

# Step 4: Check google-generativeai installation
print("[STEP 4] Checking google-generativeai Installation")
print("-"*80)
try:
    import google.generativeai as genai
    print(f"✅ google.generativeai is installed")
    print(f"   Version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")
except ImportError as e:
    print(f"❌ google-generativeai NOT installed")
    print(f"   Error: {e}")
    print(f"   Fix: pip install google-generativeai")
    print()
    print(f"STOPPING - Cannot proceed without library")
    exit(1)
print()

# Step 5: Configure API
print("[STEP 5] Configuring Gemini API")
print("-"*80)
try:
    genai.configure(api_key=api_key)
    print(f"✅ API configured successfully")
except Exception as e:
    print(f"❌ API configuration failed")
    print(f"   Error: {e}")
    print()
    print(f"STOPPING - Cannot proceed with bad API config")
    exit(1)
print()

# Step 6: List available models
print("[STEP 6] Checking Available Models")
print("-"*80)
try:
    print(f"Fetching model list from Google...")
    models = list(genai.list_models())
    print(f"✅ Retrieved {len(models)} models")
    print()
    print(f"Gemini 3 models found:")
    gemini_3_models = [m for m in models if 'gemini-3' in m.name.lower() or 'gemini3' in m.name.lower()]
    if gemini_3_models:
        for model in gemini_3_models:
            print(f"   • {model.name}")
            if hasattr(model, 'supported_generation_methods'):
                print(f"     Methods: {model.supported_generation_methods}")
    else:
        print(f"   ⚠️  No Gemini 3 models found in list")
        print(f"   Showing all available models:")
        for model in models[:10]:  # Show first 10
            print(f"   • {model.name}")
        if len(models) > 10:
            print(f"   ... and {len(models) - 10} more")
    print()
except Exception as e:
    print(f"⚠️  Could not list models: {e}")
    print(f"   This is OK - will try to use model anyway")
print()

# Step 7: Test specific model
print("[STEP 7] Testing Gemini 3 Flash Model")
print("-"*80)
MODEL_NAME = "gemini-3-flash-preview"
print(f"Model to test: {MODEL_NAME}")
print()

try:
    print(f"Initializing model...")
    model = genai.GenerativeModel(MODEL_NAME)
    print(f"✅ Model initialized successfully")
    print()
    
    print(f"Testing with simple prompt...")
    response = model.generate_content("Say 'Hello from Gemini 3 Flash' and nothing else")
    print(f"✅ Model responded!")
    print(f"   Response: {response.text}")
    print()
    
except Exception as e:
    print(f"❌ Model test FAILED")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {str(e)}")
    print()
    print(f"Full traceback:")
    traceback.print_exc()
    print()
    
    # Try alternative model names
    print(f"Trying alternative model names...")
    alternatives = [
        "gemini-3-flash",
        "gemini-pro-3-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash"
    ]
    
    for alt_model in alternatives:
        try:
            print(f"   Trying: {alt_model}... ", end="")
            test_model = genai.GenerativeModel(alt_model)
            test_response = test_model.generate_content("test")
            print(f"✅ WORKS!")
            print(f"   Use this model name: {alt_model}")
            MODEL_NAME = alt_model
            break
        except:
            print(f"❌ failed")
    
    if MODEL_NAME != "gemini-3-flash-preview":
        print(f"\n✅ Found working model: {MODEL_NAME}")
    else:
        print(f"\nSTOPPING - No working model found")
        exit(1)
print()

# Step 8: Test with JSON response
print("[STEP 8] Testing JSON Response Format")
print("-"*80)
try:
    print(f"Testing structured JSON output...")
    test_prompt = """
    Analyze this grocery item and return JSON:
    Item: Milk 2L
    Price: $5.99
    Store: Test Store
    
    Return JSON format:
    {"score": 75, "rating": "Good Buy", "reason": "Fair price"}
    """
    
    response = model.generate_content(
        test_prompt,
        generation_config={
            "response_mime_type": "application/json"
        }
    )
    
    print(f"✅ Model supports JSON output")
    print(f"   Response: {response.text[:200]}")
    
    # Try to parse it
    import json
    data = json.loads(response.text)
    print(f"✅ Response is valid JSON")
    print(f"   Parsed: {data}")
    
except Exception as e:
    print(f"❌ JSON test failed")
    print(f"   Error: {e}")
    print(f"   Traceback:")
    traceback.print_exc()
print()

# Step 9: Check if ai_quality_analyzer.py exists
print("[STEP 9] Checking ai_quality_analyzer.py")
print("-"*80)
ai_file = "ai_quality_analyzer.py"
if os.path.exists(ai_file):
    print(f"✅ {ai_file} exists")
    
    # Try to import it
    try:
        print(f"   Attempting import...")
        from ai_quality_analyzer import add_ai_analysis_to_dataframe
        print(f"   ✅ Import successful")
        
        # Check function signature
        import inspect
        sig = inspect.signature(add_ai_analysis_to_dataframe)
        print(f"   Function signature: {sig}")
        
    except Exception as e:
        print(f"   ❌ Import failed")
        print(f"   Error: {e}")
        traceback.print_exc()
else:
    print(f"❌ {ai_file} NOT found")
    print(f"   Make sure it's in the same directory as this script")
print()

# Step 10: Test with real data
print("[STEP 10] Testing with Sample Data")
print("-"*80)
if os.path.exists("current_flyers.csv"):
    try:
        import pandas as pd
        print(f"Loading current_flyers.csv...")
        df = pd.read_csv("current_flyers.csv")
        print(f"✅ Loaded {len(df)} items")
        
        # Take first 2 items
        df_test = df.head(2).copy()
        print(f"\nTesting AI analysis with 2 items...")
        
        from ai_quality_analyzer import add_ai_analysis_to_dataframe
        df_result = add_ai_analysis_to_dataframe(df_test, batch_size=2)
        
        # Check if it worked
        if df_result['ai_deal_score'].notna().any():
            print(f"✅ AI ANALYSIS WORKED!")
            print(f"\nResults:")
            print(df_result[['Item', 'Price_Value', 'ai_deal_score', 'ai_deal_rating', 'ai_explanation']].to_string(index=False))
        else:
            print(f"⚠️  AI analysis ran but didn't fill scores")
            
    except Exception as e:
        print(f"❌ Test failed")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error message: {str(e)}")
        print(f"\nFull traceback:")
        traceback.print_exc()
else:
    print(f"⚠️  current_flyers.csv not found - cannot test with real data")
    print(f"   Run your scraper first to generate data")
print()

# Final Summary
print("="*80)
print("DIAGNOSTIC COMPLETE")
print("="*80)
print()
print("Summary of findings:")
print(f"   API Key: {'✅ Present' if api_key else '❌ Missing'}")
print(f"   Library: {'✅ Installed' if 'genai' in dir() else '❌ Missing'}")
print(f"   Model: {MODEL_NAME}")
print()
print("Next steps:")
print("   1. Fix any ❌ issues above")
print("   2. Update ai_quality_analyzer.py with correct model name")
print("   3. Re-run your scraper: python get_deals.py")
print()