# 🛒 Calgary Grocery Hub

A smart grocery deal tracker that scrapes weekly flyers from Calgary stores, uses AI to categorize items, and provides historical price analysis through an interactive dashboard.

## 📋 Features

- **Automated Flyer Scraping**: Collects deals from 6+ Calgary grocery stores weekly
- **AI-Powered Categorization**: Uses Google Gemini to intelligently categorize and clean product names
- **Historical Price Tracking**: Maintains price history to identify true deals vs. inflated "sales"
- **Interactive Dashboard**: Streamlit-based UI for browsing deals and analyzing trends
- **Geographic Intelligence**: Localized to Calgary with postal code-based searches
- **Deal Analysis**: Real-time AI assessment of whether a price is actually a good deal

## 🏪 Supported Stores

- Real Canadian Superstore
- Save-On-Foods
- Calgary Co-op
- Sobeys
- Safeway
- No Frills

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))
- Network access (for scraping flyers)

### Installation

1. **Clone or download this project to your NAS**
   ```
   Y:\Python Projects\Weekly Deals\
   ```

2. **Install dependencies**
   ```bash
   cd "Y:\Python Projects\Weekly Deals"
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   # Copy the template
   cp .env.template .env
   
   # Edit .env and add your GEMINI_API_KEY
   ```

4. **Verify installation**
   ```bash
   python verify_installation.py
   ```

### Usage

#### Scrape Flyers (Run Weekly)
```bash
python get_deals.py
```

This will:
1. Fetch current flyers from all stores
2. Extract and categorize items using AI
3. Update your price history database
4. Generate clean data for the dashboard

#### Launch Dashboard
```bash
streamlit run dashboard.py
```

Access at: `http://your-nas-ip:8501`

## 📁 Project Structure

```
Weekly Deals/
├── .env                          # Your API keys (create from template)
├── .env.template                 # Template for environment variables
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── NAS_SETUP_GUIDE.md           # Detailed NAS installation guide
├── verify_installation.py        # Installation checker
│
├── get_deals.py                  # Main scraper script
├── classifier.py                 # AI categorization module
├── dashboard.py                  # Streamlit dashboard
│
├── seton_grocery_history.csv     # Raw historical data
└── clean_grocery_data.csv        # Processed data (auto-generated)
```

## 🔄 Automation

### Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task → "Weekly Grocery Scraper"
3. Trigger: Weekly (Monday 6 AM recommended)
4. Action: Start a program
   - Program: `python`
   - Arguments: `"Y:\Python Projects\Weekly Deals\get_deals.py"`
   - Start in: `Y:\Python Projects\Weekly Deals`

### Linux/Mac Cron

```bash
# Run every Monday at 6 AM
0 6 * * 1 cd /path/to/project && python get_deals.py
```

## 🎯 Dashboard Features

### Current Deals Tab
- Browse all active flyer items
- Filter by store, category, sub-category
- Sort by price, savings %, or expiration
- Search for specific products
- AI-powered deal analysis with historical context

### Ask Data Tab
- Natural language queries about prices and trends
- Automatic chart generation
- Compare stores and track price changes
- Examples:
  - "Compare current butter prices to last month"
  - "Show me the cheapest protein options this week"
  - "Which store has the best deals on produce?"

## 🗄️ Database Schema

### seton_grocery_history.csv (Raw Data)
- `Date`: When item was scraped
- `Store`: Store name
- `Original_Name`: Raw product name from flyer
- `Item`: AI-cleaned product name
- `Category`: Primary category
- `Sub_Category`: Detailed category
- `Price_Text`: Original price text from flyer
- `Price_Value`: Numeric price for analysis
- `Valid_Until`: Deal expiration date

### clean_grocery_data.csv (Dashboard Data)
- All above fields plus:
- `display_category`: User-friendly category names
- `savings_pct`: Calculated savings percentage
- `original_price`: Regular price (when available)

## 🔮 Roadmap

### Phase 1: Core Functionality ✅
- [x] Flyer scraping
- [x] AI categorization
- [x] Historical tracking
- [x] Dashboard with filtering

### Phase 2: Database Migration (In Progress)
- [ ] Migrate to Supabase PostgreSQL
- [ ] Add geographic indexing
- [ ] Real-time price updates
- [ ] User preferences storage

### Phase 3: Mobile Scanner
- [ ] Barcode scanning interface
- [ ] Real-time deal verification
- [ ] Location-based recommendations
- [ ] Shopping list integration

### Phase 4: Advanced Analytics
- [ ] Price prediction models
- [ ] Seasonal trend analysis
- [ ] Store comparison scoring
- [ ] Deal alerts and notifications

## 🛠️ Troubleshooting

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### Scraper returns no results
- Check your internet connection
- Verify postal code in .env or get_deals.py
- Ensure Gemini API key is valid

### Dashboard won't load
- Check that Streamlit is installed: `pip install streamlit`
- Try specifying host: `streamlit run dashboard.py --server.address 0.0.0.0`
- Check firewall allows port 8501

### AI categorization fails
- Verify GEMINI_API_KEY in .env
- Check API quota at https://makersuite.google.com
- Review classifier.py for errors

## 📊 Data Privacy

- All data is stored locally on your NAS
- No personal information is collected
- Flyer data is public information
- AI categorization happens via Google's API (product names only)

## 🤝 Contributing

This is a personal project, but suggestions are welcome!

## 📝 License

Personal use project - modify as needed for your own grocery tracking needs.

## 🙏 Acknowledgments

- Flipp API for flyer data
- Google Gemini for AI categorization
- Streamlit for the dashboard framework

---

**Questions?** Check the [NAS_SETUP_GUIDE.md](NAS_SETUP_GUIDE.md) for detailed installation help.
