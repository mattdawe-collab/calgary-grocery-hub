# Calgary Grocery Hub - NAS Installation Guide

## Prerequisites
- Python 3.8+ installed on your NAS
- Network access to your NAS (\\192.168.1.78)
- SSH or terminal access to NAS (optional but recommended)

## Step 1: Directory Structure
Your project should be organized like this on the NAS:

```
Y:\Python Projects\Weekly Deals\
├── .env                          # API keys and secrets
├── .gitignore                    # Git ignore file
├── requirements.txt              # Python dependencies
├── classifier.py                 # AI categorization (missing from upload)
├── get_deals.py                  # Scraper script
├── dashboard.py                  # Streamlit dashboard
├── seton_grocery_history.csv     # Historical data
├── clean_grocery_data.csv        # Processed data (generated)
└── Flyers/                       # (optional) Store flyer archives
```

## Step 2: Create .env File
Create a `.env` file in the project root with:

```env
# Gemini AI
GEMINI_API_KEY=your_gemini_api_key_here

# Supabase (when ready)
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Optional: Database
DATABASE_URL=postgresql://user:password@localhost/grocery_db
```

## Step 3: Install Dependencies

### Option A: Using Command Prompt (Windows NAS)
```cmd
cd "Y:\Python Projects\Weekly Deals"
python -m pip install -r requirements.txt
```

### Option B: Using PowerShell
```powershell
cd "Y:\Python Projects\Weekly Deals"
python -m pip install -r requirements.txt
```

### Option C: If NAS runs Linux
```bash
cd "/mnt/your_share/Python Projects/Weekly Deals"
pip install -r requirements.txt
```

## Step 4: Missing File - classifier.py
**IMPORTANT**: You reference `classifier.py` in your code but it wasn't uploaded.
This file should contain the `categorize_groceries()` function.

If you don't have this file, I can create a basic version using Gemini AI.

## Step 5: Run the Scraper
```bash
python get_deals.py
```

This will:
1. Scrape flyers from Calgary stores
2. Categorize items using AI
3. Update `seton_grocery_history.csv`
4. Generate `clean_grocery_data.csv`

## Step 6: Run the Dashboard
```bash
streamlit run dashboard.py
```

Access at: `http://192.168.1.78:8501` (or whatever port Streamlit assigns)

## Step 7: Schedule Automatic Updates

### Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Daily (or when you want flyers updated)
4. Action: Start a program
5. Program: `python`
6. Arguments: `"Y:\Python Projects\Weekly Deals\get_deals.py"`
7. Start in: `Y:\Python Projects\Weekly Deals`

### Linux Cron
```bash
# Edit crontab
crontab -e

# Run scraper every Monday at 6 AM
0 6 * * 1 cd /path/to/project && python get_deals.py
```

## Troubleshooting

### Issue: "Module not found"
- Make sure you installed requirements: `pip install -r requirements.txt`
- Check Python version: `python --version` (need 3.8+)

### Issue: "classifier.py not found"
- This file is missing from your uploads
- Let me know and I'll create it for you

### Issue: Can't access Streamlit dashboard
- Check firewall rules on NAS
- Verify Streamlit port (default 8501)
- Try: `streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0`

### Issue: Scraper fails
- Check internet connection from NAS
- Verify Gemini API key is valid
- Check postal code is correct (currently: T3M1M9)

## Network Access
If accessing from other devices on your network:
- Dashboard: `http://192.168.1.78:8501`
- Ensure NAS firewall allows incoming connections on port 8501

## Next Steps
1. ✅ Install dependencies
2. ✅ Create .env file with API keys
3. ✅ Get/create classifier.py
4. ✅ Run scraper once manually to test
5. ✅ Launch dashboard and verify
6. ✅ Set up scheduled task for automatic updates
7. ⏭️ Migrate to Supabase database
8. ⏭️ Build mobile scanner interface
