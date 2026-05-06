"""
NAS Installation Verification Script
Run this to check if your Calgary Grocery Hub is properly configured
"""

import sys
import os
from pathlib import Path

print("=" * 60)
print("Calgary Grocery Hub - NAS Installation Checker")
print("=" * 60)

# Check Python Version
print("\n1. Python Version Check")
print(f"   Current: Python {sys.version}")
if sys.version_info >= (3, 8):
    print("   ✅ Python version is compatible (3.8+)")
else:
    print("   ❌ Python version too old. Need 3.8 or higher.")

# Check Required Files
print("\n2. Required Files Check")
required_files = [
    'get_deals.py',
    'dashboard.py',
    'requirements.txt',
    'seton_grocery_history.csv'
]

missing_files = []
for file in required_files:
    if os.path.exists(file):
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - NOT FOUND")
        missing_files.append(file)

# Check Optional Files
print("\n3. Optional Files Check")
optional_files = [
    '.env',
    'classifier.py',
    'clean_grocery_data.csv'
]

for file in optional_files:
    if os.path.exists(file):
        print(f"   ✅ {file}")
    else:
        print(f"   ⚠️  {file} - NOT FOUND (may be generated or needed)")

# Check Dependencies
print("\n4. Python Dependencies Check")
dependencies = [
    'streamlit',
    'pandas',
    'plotly',
    'requests',
    'dotenv',
    'anthropic',
    'sqlalchemy'
]

missing_deps = []
for dep in dependencies:
    try:
        if dep == 'dotenv':
            __import__('dotenv')
        else:
            __import__(dep)
        print(f"   ✅ {dep}")
    except ImportError:
        print(f"   ❌ {dep} - NOT INSTALLED")
        missing_deps.append(dep)

# Check .env Configuration
print("\n5. Environment Configuration Check")
if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()
    
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if anthropic_key:
        print(f"   ✅ ANTHROPIC_API_KEY is set ({anthropic_key[:10]}...)")
    else:
        print("   ❌ ANTHROPIC_API_KEY not found in .env")
    
    supabase_url = os.getenv('SUPABASE_URL')
    if supabase_url:
        print(f"   ✅ SUPABASE_URL is set")
    else:
        print("   ⚠️  SUPABASE_URL not set (optional for now)")
else:
    print("   ❌ .env file not found - create one with your API keys")

# Check Data Files
print("\n6. Data Files Check")
if os.path.exists('seton_grocery_history.csv'):
    import pandas as pd
    try:
        df = pd.read_csv('seton_grocery_history.csv')
        print(f"   ✅ History file loaded: {len(df)} records")
        print(f"   📊 Columns: {', '.join(df.columns.tolist()[:5])}...")
    except Exception as e:
        print(f"   ❌ Error reading history file: {e}")

# Network Check
print("\n7. Network Configuration")
import socket
hostname = socket.gethostname()
ip_address = socket.gethostbyname(hostname)
print(f"   🌐 Hostname: {hostname}")
print(f"   🌐 IP Address: {ip_address}")
print(f"   📝 Dashboard URL will be: http://{ip_address}:8501")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if missing_files:
    print(f"❌ Missing {len(missing_files)} required file(s): {', '.join(missing_files)}")
else:
    print("✅ All required files present")

if missing_deps:
    print(f"❌ Missing {len(missing_deps)} dependencies")
    print(f"   Run: pip install {' '.join(missing_deps)}")
else:
    print("✅ All dependencies installed")

if not os.path.exists('.env'):
    print("❌ Need to create .env file with API keys")
elif not os.getenv('ANTHROPIC_API_KEY'):
    print("❌ Need to add ANTHROPIC_API_KEY to .env")
else:
    print("✅ Environment configured")

print("\n" + "=" * 60)

if not missing_files and not missing_deps and os.path.exists('.env'):
    print("🎉 Your installation looks good! Ready to run:")
    print("   - Scraper: python get_deals.py")
    print("   - Dashboard: streamlit run dashboard.py")
else:
    print("⚠️  Please fix the issues above before running the project")
    
print("=" * 60)
