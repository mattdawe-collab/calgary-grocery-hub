# 🔍 Flipp Scraper API Diagnostic Report

**Date:** January 7, 2026  
**Issue:** Dead API endpoints preventing scraper from working

---

## 🚨 Problem Summary

Your scraper uses multiple Flipp API endpoints, and based on the code structure, several appear to be failing or deprecated.

---

## 📋 API Endpoint Status

### **1. Flyer List Endpoint (Phase 1)**

**Current endpoint in your script:**
```
https://backflipp.wishabi.com/flipp/flyers
```

**Status:** ⚠️ **LIKELY DEAD**

**Alternative endpoints to try:**
- `https://backflipp.wishabi.com/flyers` (without /flipp/)
- `https://flipp.com/api/flyers`
- `https://shopping.flipp.com/api/v3/flyers`

---

### **2. Item Endpoints (Phase 2)**

#### **Public API (Fallback Path)**

**Current endpoint:**
```
https://backflipp.wishabi.com/flipp/flyers/{flyer_id}/items
```

**Status:** ❌ **LIKELY DEAD** - This is probably your main problem

**Evidence:**
- Your debug output shows "No items retrieved" for stores without enterprise tokens
- Public API is used as fallback when enterprise tokens fail

---

#### **Enterprise API (Primary Path)**

**Current endpoint:**
```
https://dam.flippenterprise.net/flyerkit/publication/{flyer_id}/products
```

**Status:** ✅ **PROBABLY WORKING**

**Stores using this:**
- ✅ No Frills (token: `1063f92aaf17b3dfa830cd70a685a52b`)
- ✅ Superstore (token: `a6e07e290f469d032d54a252f7582de2`)
- ✅ Calgary Co-op (token: `3e491961d82170af5a2044e66ea4a1a1`)
- ✅ Sobeys (token: `afbc75b4e335236182ac2fba092a0d4a`)
- ✅ Safeway (same token as Sobeys)

---

## 🎯 Stores Affected

### **Working (Have Enterprise Tokens):**
1. No Frills
2. Superstore  
3. Calgary Co-op
4. Sobeys
5. Safeway

### **Broken (Need Public API):**
1. ❌ **Walmart** - No enterprise token, relies on dead public API
2. ❌ Any other stores without tokens in your config

---

## 🔧 Immediate Fixes

### **Option 1: Quick Fix - Remove Broken Stores**

Edit your `STORE_LIST`:

```python
# Remove Walmart temporarily
STORE_LIST = [
    "Real Canadian Superstore", 
    "Sobeys", 
    # "Walmart",  # Temporarily disabled - no working API
    "Calgary Co-op", 
    "Safeway", 
    "No Frills"
]
```

---

### **Option 2: Add Walmart Token (If Available)**

Check if Walmart has an enterprise token:
- Contact Flipp Enterprise
- Check Walmart's flyer page source for tokens
- May require business account

---

### **Option 3: Update Public API Endpoint**

Try alternative paths for the public API:

```python
# In download_flyer_items function, replace:
url = f"https://backflipp.wishabi.com/flipp/flyers/{flyer_id}/items"

# With alternatives:
alternatives = [
    f"https://backflipp.wishabi.com/flyers/{flyer_id}/items",
    f"https://backflipp.wishabi.com/flipp/flyers/{flyer_id}",
    f"https://backflipp.wishabi.com/flyers/{flyer_id}",
]
```

---

## 🧪 Testing & Diagnosis

### **Step 1: Run the Diagnostic Script**

I created `test_api_endpoints.py` for you. Run it to identify working endpoints:

```bash
python test_api_endpoints.py
```

This will:
- Test all known Flipp API variations
- Show which endpoints return data
- Provide specific error messages
- Generate a detailed report

---

### **Step 2: Check Enterprise Tokens**

Your enterprise tokens might have expired. Test them:

```bash
# Test Co-op token
curl "https://dam.flippenterprise.net/flyerkit/publication/YOUR_FLYER_ID/products?display_type=all&locale=en&access_token=3e491961d82170af5a2044e66ea4a1a1"
```

Replace `YOUR_FLYER_ID` with an actual flyer ID from the first API call.

---

### **Step 3: Check Flipp's Official Documentation**

1. Visit: https://flipp.com/developers (if it exists)
2. Check for API changelog or deprecation notices
3. Look for new API endpoints

---

## 🚀 Long-Term Solutions

### **Solution 1: Use Enhanced Scraper (Provided)**

I created `get_deals_v3_enhanced.py` with:
- ✅ Multiple endpoint fallbacks
- ✅ Better error handling
- ✅ Automatic endpoint testing
- ✅ Detailed diagnostic output

To use:
```bash
python get_deals_v3_enhanced.py
```

---

### **Solution 2: Switch to Browser Automation**

If APIs are truly dead, use Selenium/Playwright:

**Pros:**
- Scrapes actual website (always works if site works)
- Not dependent on API changes
- Can handle dynamic content

**Cons:**
- Slower
- More complex
- Requires browser driver

**Example with Playwright:**
```python
from playwright.sync_api import sync_playwright

def scrape_flipp_playwright(postal_code):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"https://flipp.com/?postal_code={postal_code}")
        
        # Wait for flyers to load
        page.wait_for_selector('.flyer-card')
        
        # Extract flyer data
        flyers = page.query_selector_all('.flyer-card')
        # ... rest of scraping logic
```

---

### **Solution 3: Official Flipp Integration**

Contact Flipp directly:
- Email: developers@flipp.com (if it exists)
- Request official API access
- Ask about enterprise partnerships

---

## 📝 Action Plan

### **Immediate (Today):**

1. ✅ Run `test_api_endpoints.py` to confirm which endpoints work
2. ✅ Test enterprise tokens are still valid
3. ✅ Use `get_deals_v3_enhanced.py` which has fallbacks built-in

---

### **Short-term (This Week):**

1. Remove Walmart from store list (or find its token)
2. Monitor scraper logs for other failures
3. Document which endpoints actually work

---

### **Long-term (This Month):**

1. Consider browser automation backup
2. Set up monitoring/alerting for API failures
3. Contact Flipp about official API access

---

## 🔍 How to Identify Dead Links Yourself

### **Method 1: Check HTTP Response**

```python
import requests

url = "https://backflipp.wishabi.com/flipp/flyers/12345/items"
response = requests.get(url)

if response.status_code == 404:
    print("❌ Endpoint is DEAD (404)")
elif response.status_code == 403:
    print("⚠️ Endpoint exists but access denied")
elif response.status_code == 200:
    print("✅ Endpoint is ALIVE")
```

---

### **Method 2: Compare Response Structure**

```python
# Old working response
{'items': [...]}

# Dead endpoint response
{'error': 'Not found'} or empty or different structure
```

---

### **Method 3: Check Browser Network Tab**

1. Open flipp.com in browser
2. Open DevTools (F12)
3. Go to Network tab
4. Load a flyer
5. Look for XHR/Fetch requests
6. Copy the working endpoint URLs

---

## 📊 Expected Outcomes

### **After running test_api_endpoints.py:**

**Best case:**
```
✅ Found working alternative endpoints
→ Update your scraper to use these
```

**Moderate case:**
```
⚠️ Enterprise API works, public API dead
→ Remove Walmart, keep other stores
```

**Worst case:**
```
❌ All endpoints dead
→ Switch to browser automation
→ Contact Flipp for API access
```

---

## 🆘 Need More Help?

If the diagnostic script doesn't solve it:

1. **Share the test output** - Run `test_api_endpoints.py` and share results
2. **Check browser network** - See what endpoints flipp.com actually uses
3. **Try from different location** - Might be regional API endpoints
4. **Check for rate limiting** - You might be blocked temporarily

---

## 📚 Additional Resources

- **Your original script:** Uses hybrid approach (smart!)
- **Enhanced script:** Has multiple fallbacks built-in
- **Test script:** Identifies working endpoints

All three files are now in your `/home/claude/` directory.

---

## ✅ Quick Start

**Right now, do this:**

```bash
# 1. Test the endpoints
python test_api_endpoints.py > api_test_results.txt

# 2. Review the results
cat api_test_results.txt

# 3. Try the enhanced scraper
python get_deals_v3_enhanced.py
```

This will immediately tell you:
- Which endpoints are alive
- Which stores will work
- What needs to be fixed

---

**Questions? Check these first:**

❓ "How do I know if an endpoint is dead?"
→ Run the test script, it checks everything

❓ "Can I fix this without changing code?"
→ Probably not, API structure has changed

❓ "Should I use browser automation instead?"
→ Only if all API endpoints truly fail

❓ "What if enterprise tokens expired?"
→ You'll need to contact the stores or Flipp

---

*Last updated: January 7, 2026*
