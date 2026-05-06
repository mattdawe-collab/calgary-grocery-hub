# 🚀 NAS Deployment Checklist

Use this checklist to ensure everything is properly set up on your NAS at `\\192.168.1.78\Python Projects\Weekly Deals\`

## ☑️ Pre-Installation

- [ ] Python 3.8+ is installed on NAS
- [ ] You have SSH/terminal access to NAS (or can run commands via Windows)
- [ ] You have your Google Gemini API key ready ([Get one](https://makersuite.google.com/app/apikey))

## ☑️ File Transfer

Copy these files to `Y:\Python Projects\Weekly Deals\`:

**Required Files:**
- [ ] `get_deals.py` (your existing scraper)
- [ ] `dashboard.py` (your existing dashboard)
- [ ] `classifier.py` (your existing AI classifier)
- [ ] `requirements.txt` (UPDATED version from this session)
- [ ] `seton_grocery_history.csv` (your existing data)

**New Files from This Session:**
- [ ] `.env.template` → rename to `.env` after copying
- [ ] `.gitignore`
- [ ] `README.md`
- [ ] `NAS_SETUP_GUIDE.md`
- [ ] `SDK_COMPATIBILITY.md`
- [ ] `verify_installation.py`

## ☑️ Configuration

### 1. Create .env File
- [ ] Copy `.env.template` to `.env`
- [ ] Edit `.env` and add your `GEMINI_API_KEY`
- [ ] Verify postal code is `T3M1M9` (or update for your area)

### 2. Install Dependencies
```bash
cd "Y:\Python Projects\Weekly Deals"
pip install -r requirements.txt
```

Check off when installed:
- [ ] streamlit
- [ ] pandas
- [ ] plotly
- [ ] python-dotenv
- [ ] google-genai (NEW SDK)
- [ ] google-generativeai (OLD SDK)
- [ ] pydantic
- [ ] requests
- [ ] sqlalchemy
- [ ] supabase (optional for now)

## ☑️ Verification

### 1. Run Installation Check
```bash
python verify_installation.py
```

Expected output:
- [ ] ✅ Python version 3.8+
- [ ] ✅ All required files present
- [ ] ✅ All dependencies installed
- [ ] ✅ GEMINI_API_KEY configured
- [ ] ✅ History CSV readable

### 2. Test Scraper
```bash
python get_deals.py
```

Expected behavior:
- [ ] Finds flyers for Calgary stores
- [ ] Extracts items from flyers
- [ ] AI categorizes items (may take a few minutes)
- [ ] Updates `seton_grocery_history.csv`
- [ ] Creates `clean_grocery_data.csv`

### 3. Test Dashboard
```bash
streamlit run dashboard.py
```

Expected behavior:
- [ ] Opens browser to `http://192.168.1.78:8501`
- [ ] Shows "Calgary Grocery Hub" title
- [ ] Current Deals tab shows items
- [ ] Can filter by store/category
- [ ] Ask Data tab responds to queries

## ☑️ Network Access

Test from other devices on your network:

### From Windows PC:
- [ ] Can access `http://192.168.1.78:8501`

### From Phone:
- [ ] Can access `http://192.168.1.78:8501` in mobile browser

### Troubleshooting:
If dashboard not accessible:
- [ ] Check NAS firewall allows port 8501
- [ ] Try running with: `streamlit run dashboard.py --server.address 0.0.0.0`
- [ ] Verify IP with `ipconfig` (Windows) or `ifconfig` (Linux)

## ☑️ Automation Setup

### Option A: Windows Task Scheduler
- [ ] Open Task Scheduler
- [ ] Create new Basic Task: "Weekly Grocery Scraper"
- [ ] Trigger: Weekly, Monday, 6:00 AM
- [ ] Action: Start a program
  - Program: `python`
  - Arguments: `get_deals.py`
  - Start in: `Y:\Python Projects\Weekly Deals`
- [ ] Test: Right-click task → Run
- [ ] Verify: Check if CSV files updated

### Option B: Cron (Linux NAS)
```bash
crontab -e
# Add line:
0 6 * * 1 cd /path/to/project && python get_deals.py
```
- [ ] Cron job added
- [ ] Test with: `crontab -l` (should show the job)

## ☑️ Data Backup

Set up backup for:
- [ ] `seton_grocery_history.csv` (your historical price data)
- [ ] `.env` file (contains API key)
- [ ] Entire project folder (recommended)

Backup location: ___________________________

## ☑️ Known Issues & Solutions

### Issue: "Module 'google.generativeai' has no attribute 'Client'"
**Solution**: This is expected! Your code uses TWO different Gemini SDKs:
- `classifier.py` uses `google-genai` (new SDK)
- `dashboard.py` uses `google.generativeai` (old SDK)
Both are installed in requirements.txt.

### Issue: Scraper finds 0 items
**Solution**: 
- Check internet connection from NAS
- Verify postal code in get_deals.py (line 22)
- Check if Flipp API is accessible

### Issue: AI categorization fails
**Solution**:
- Verify GEMINI_API_KEY is correct in .env
- Check API quota at https://makersuite.google.com
- Try running `classifier.py` directly to test

### Issue: Dashboard shows no data
**Solution**:
- Run scraper first: `python get_deals.py`
- Check that `clean_grocery_data.csv` exists
- Verify CSV has data: `wc -l clean_grocery_data.csv`

## ☑️ Post-Setup

After everything works:
- [ ] Document your NAS IP in a safe place
- [ ] Set a calendar reminder to check scraper is running
- [ ] Star/bookmark the Gemini API console
- [ ] Read SDK_COMPATIBILITY.md (for future migration)

## 🎯 Next Phase: Database Migration

Once stable, migrate to Supabase:
- [ ] Set up Supabase project
- [ ] Add SUPABASE_URL and SUPABASE_KEY to .env
- [ ] Create migration script (I can help!)
- [ ] Test Supabase connection
- [ ] Build mobile scanner interface

---

## 📝 Notes

Date installed: ___________________________

Issues encountered: ___________________________

___________________________

___________________________

Working dashboard URL: ___________________________

Scheduled scraper: ⬜ Not set up  ⬜ Task Scheduler  ⬜ Cron

---

**Need Help?** Check the README.md and NAS_SETUP_GUIDE.md files!
