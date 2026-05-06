"""
Calgary Grocery Hub Dashboard v2.1
- 🔍 Direct search with autocomplete
- 📂 Category → Subcategory cascade filtering  
- 🏆 Best deals per store prioritized
- 🎯 Multi-level sorting (store → score/savings/order)
- ⏳ Scraper-aware (handles incomplete data gracefully)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime
import warnings

warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

# === CONFIGURATION ===
st.set_page_config(
    page_title="Calgary Grocery Hub",
    layout="wide",
    page_icon="🛒"
)

# Files
CURRENT_FLYERS = "current_flyers.csv"
HISTORICAL_ARCHIVE = "historical_archive.csv"
FALLBACK_FILE = "clean_grocery_data.csv"

# ALL categories (always shown, even if empty)
ALL_CATEGORIES = [
    "Produce", "Beef", "Pork", "Poultry", "Lamb", "Seafood",
    "Dairy & Eggs", "Bakery", "Pantry", "Frozen", "Beverages",
    "Household & Personal", "Snacks", "Other"
]

CATEGORY_ICONS = {
    "Produce": "🥬", "Beef": "🥩", "Pork": "🐷", "Poultry": "🍗",
    "Lamb": "🐑", "Seafood": "🐟", "Dairy & Eggs": "🥛", "Bakery": "🥖",
    "Pantry": "🍝", "Frozen": "❄️", "Beverages": "🥤",
    "Household & Personal": "🧹", "Snacks": "🍿", "Other": "📦"
}

# === DATA LOADING (CACHED!) ===

@st.cache_data(ttl=60)  # Refresh every minute during scraping
def load_current_deals():
    """Load current flyer data - scraper-aware"""
    if os.path.exists(CURRENT_FLYERS):
        df = pd.read_csv(CURRENT_FLYERS)
    elif os.path.exists(FALLBACK_FILE):
        df = pd.read_csv(FALLBACK_FILE)
    else:
        return None
    
    # Handle dates
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if 'Valid_Until' in df.columns:
        df['Valid_Until'] = pd.to_datetime(df['Valid_Until'], errors='coerce')
    
    # Standardize category columns
    if 'ai_category' in df.columns:
        df['display_category'] = df['ai_category'].fillna('Other')
        df['display_subcategory'] = df['ai_sub_category'].fillna('')
    else:
        df['display_category'] = df.get('Category', 'Other')
        df['display_subcategory'] = df.get('Sub_Category', '')
    
    # Ensure categories are valid
    df['display_category'] = df['display_category'].apply(
        lambda x: x if x in ALL_CATEGORIES else 'Other'
    )
    
    return df

@st.cache_data(ttl=600)
def load_historical_data():
    """Load historical archive"""
    if not os.path.exists(HISTORICAL_ARCHIVE):
        return None
    
    try:
        df = pd.read_csv(HISTORICAL_ARCHIVE)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # Remove rows with invalid dates
        df = df.dropna(subset=['Date'])
        
        if 'ai_category' in df.columns:
            df['display_category'] = df['ai_category'].fillna('Other')
        else:
            df['display_category'] = df.get('Category', 'Other')
        
        return df
    except Exception:
        return None

def get_subcategories(df, category):
    """Get subcategories for a category"""
    if category == 'All Categories':
        return []
    
    subcats = df[df['display_category'] == category]['display_subcategory'].unique()
    subcats = [s for s in subcats if s and str(s).strip() and str(s) != 'nan']
    return sorted(subcats)

@st.cache_data
def get_item_history(item_name, _df_history):
    """Get price history for item - cached"""
    if _df_history is None or len(_df_history) == 0:
        return None
    
    matches = _df_history[_df_history['Item'].str.contains(item_name, case=False, na=False, regex=False)]
    
    if len(matches) < 2:
        return None
    
    # Remove any rows with NaT dates
    matches = matches.dropna(subset=['Date'])
    
    if len(matches) < 2:
        return None
    
    matches = matches.sort_values('Date').tail(10)
    
    cols = ['Date', 'Price_Value', 'Store']
    if 'ai_deal_score' in matches.columns:
        cols.append('ai_deal_score')
    
    return matches[cols].copy()

def create_price_chart(trend_data, current_price=None):
    """Create price history chart"""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=trend_data['Date'],
        y=trend_data['Price_Value'],
        mode='lines+markers',
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=8),
        text=trend_data['Store'],
        hovertemplate='<b>%{text}</b><br>%{x|%b %d}<br>$%{y:.2f}<extra></extra>'
    ))
    
    avg_price = trend_data['Price_Value'].mean()
    fig.add_hline(y=avg_price, line_dash="dash", line_color="gray",
                  annotation_text=f"Avg: ${avg_price:.2f}", annotation_position="right")
    
    if current_price:
        fig.add_hline(y=current_price, line_dash="dot",
                      line_color="red" if current_price < avg_price else "green",
                      annotation_text=f"Today: ${current_price:.2f}", annotation_position="left")
    
    fig.update_layout(
        xaxis_title="Date", yaxis_title="Price ($)",
        height=200, margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False, hovermode='x unified'
    )
    
    return fig

def display_deal_card(row, idx, has_ai, df_history):
    """Display a single deal card"""
    icon = CATEGORY_ICONS.get(row['display_category'], "📦")
    
    # Build title
    if has_ai:
        score = row.get('ai_deal_score', 0)
        badge = "🌟" if score >= 80 else "✅" if score >= 60 else "⚪"
        title = f"{badge} {icon} {row['Item']} - **${row['Price_Value']:.2f}** @ {row['Store']}"
    else:
        title = f"{icon} {row['Item']} - **${row['Price_Value']:.2f}** @ {row['Store']}"
    
    with st.expander(title, expanded=False):
        cols = st.columns([2, 1, 1])
        
        with cols[0]:
            st.write(f"**Category:** {row['display_category']}")
            if pd.notna(row.get('display_subcategory')) and row['display_subcategory']:
                st.write(f"**Type:** {row['display_subcategory']}")
            # v3.2: ai_brand was removed from the v3.x schema; ai_normalized_name
            # is the closest replacement. Fall back gracefully if neither is set.
            normalized = row.get('ai_normalized_name')
            if has_ai and pd.notna(normalized) and normalized and normalized != row.get('Item'):
                st.write(f"**Normalized:** {normalized}")
        
        with cols[1]:
            st.write(f"**Price:** ${row['Price_Value']:.2f}")
            if pd.notna(row.get('Normalized_Price')):
                st.write(f"{row['Normalized_Price']}")
        
        with cols[2]:
            if has_ai:
                score = row.get('ai_deal_score', 0)
                rating = row.get('ai_deal_rating', 'unknown')
                
                # Show score prominently
                if score >= 80:
                    st.success(f"**Score: {score}/100**")
                    st.caption(f"⭐ {rating.title()}")
                elif score >= 60:
                    st.info(f"**Score: {score}/100**")
                    st.caption(f"👍 {rating.title()}")
                elif score >= 40:
                    st.warning(f"**Score: {score}/100**")
                    st.caption(f"👌 {rating.title()}")
                else:
                    st.error(f"**Score: {score}/100**")
                    st.caption(f"👎 {rating.title()}")
                
                # Show confidence
                confidence = row.get('ai_confidence', 'unknown')
                st.caption(f"Confidence: {confidence}")
        
        # AI insights (v3.2: schema renamed ai_recommendation -> ai_explanation;
        # ai_has_anomaly/ai_anomaly_type are no longer produced).
        if has_ai:
            explanation = row.get('ai_explanation')
            if pd.notna(explanation) and explanation:
                st.markdown("---")
                st.info(f"💡 **AI:** {explanation}")
        
        # Price history - TEXT-BASED (easier to read!)
        if df_history is not None:
            history = get_item_history(row['Item'], df_history)
            if history is not None and len(history) >= 2:
                st.markdown("---")
                st.markdown("**📊 Price History:**")
                
                # Calculate stats
                avg_price = history['Price_Value'].mean()
                min_price = history['Price_Value'].min()
                max_price = history['Price_Value'].max()
                current = row['Price_Value']
                
                # Sort by date descending (most recent first), filtering out NaT
                history_sorted = history[pd.notna(history['Date'])].sort_values('Date', ascending=False)
                
                # Display summary
                hist_cols = st.columns(3)
                
                with hist_cols[0]:
                    st.metric("Average Price", f"${avg_price:.2f}")
                    if current < avg_price:
                        st.caption(f"✅ ${avg_price - current:.2f} below avg")
                    elif current > avg_price:
                        st.caption(f"⚠️ ${current - avg_price:.2f} above avg")
                    else:
                        st.caption("➖ At average")
                
                with hist_cols[1]:
                    st.metric("Price Range", f"${min_price:.2f} - ${max_price:.2f}")
                    if current == min_price:
                        st.caption("🎯 Lowest ever!")
                    elif current == max_price:
                        st.caption("⚠️ Highest seen")
                
                with hist_cols[2]:
                    st.metric("Times on Sale", f"{len(history)}")
                    
                    # Last sale date (excluding today)
                    today = pd.Timestamp.now().normalize()
                    past_sales = history_sorted[
                        (history_sorted['Date'] < today) & 
                        (pd.notna(history_sorted['Date']))  # Exclude NaT dates
                    ]
                    if len(past_sales) > 0:
                        last_sale = past_sales.iloc[0]
                        if pd.notna(last_sale['Date']):
                            days_ago = (today - last_sale['Date']).days
                            st.caption(f"Last: {days_ago} days ago")
                
                # Show recent sales
                st.markdown("**Recent Sales:**")
                for idx, sale in history_sorted.head(5).iterrows():
                    # Handle NaT dates safely
                    if pd.isna(sale['Date']):
                        date_str = "Unknown date"
                    else:
                        date_str = sale['Date'].strftime('%b %d, %Y')
                    
                    price_str = f"${sale['Price_Value']:.2f}"
                    store_str = sale['Store']
                    
                    # Add indicator
                    if sale['Price_Value'] < avg_price:
                        indicator = "🟢"  # Good deal
                    elif sale['Price_Value'] > avg_price:
                        indicator = "🔴"  # Above average
                    else:
                        indicator = "⚪"  # At average
                    
                    st.caption(f"{indicator} **{price_str}** @ {store_str} • {date_str}")


# === MAIN APP ===

st.title("🛒 Calgary Grocery Hub")
st.caption("AI-Powered Grocery Deal Finder")

# Load data
df_current = load_current_deals()

if df_current is None:
    st.error("📭 No data found! Run `python get_deals.py` to scrape flyers.")
    st.info("💡 **Tip:** The scraper takes 5-10 minutes. Refresh this page once complete.")
    st.stop()

# Check if data is complete
has_ai = 'ai_deal_score' in df_current.columns
is_partial = len(df_current) < 100

if is_partial:
    st.warning("⏳ **Data appears incomplete.** Scraper may still be running.")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# === SIDEBAR: FILTERS ===

st.sidebar.title("🔍 Search & Filter")

# SEARCH BAR
search_term = st.sidebar.text_input(
    "🔎 Search items",
    placeholder="e.g., chicken, beef, milk...",
    help="Search by item name"
)

st.sidebar.markdown("---")

# STORE FILTER
stores = ['All Stores'] + sorted(df_current['Store'].unique().tolist())
selected_store = st.sidebar.selectbox("🏪 Store", stores)

# CATEGORY FILTER (always show all)
categories_with_counts = {cat: len(df_current[df_current['display_category'] == cat]) for cat in ALL_CATEGORIES}

categories_display = ['All Categories'] + [f"{cat} ({categories_with_counts[cat]})" for cat in ALL_CATEGORIES]

selected_category_display = st.sidebar.selectbox("📂 Category", categories_display)

# Extract category name
selected_category = selected_category_display.split(' (')[0] if selected_category_display != 'All Categories' else 'All Categories'

# SUBCATEGORY FILTER (cascade)
if selected_category != 'All Categories':
    subcategories = get_subcategories(df_current, selected_category)
    
    if subcategories:
        selected_subcategory = st.sidebar.selectbox(
            "📑 Subcategory",
            ['All Subcategories'] + subcategories
        )
    else:
        selected_subcategory = 'All Subcategories'
        st.sidebar.caption("ℹ️ No subcategories")
else:
    selected_subcategory = 'All Subcategories'

# PRICE RANGE
# v3.2: guard against an empty/all-NaN price column (would otherwise pass
# nan into st.sidebar.slider, which crashes the dashboard with a cryptic
# "value 'nan' is not in range" error).
st.sidebar.markdown("---")
_price_col = pd.to_numeric(df_current['Price_Value'], errors='coerce')
if _price_col.notna().any():
    price_max = float(_price_col.max())
else:
    price_max = 100.0
slider_top = max(1.0, min(price_max, 100.0))
min_price, max_price = st.sidebar.slider(
    "💰 Price Range",
    0.0, slider_top,
    (0.0, min(50.0, slider_top)),
    format="$%.2f"
)

# AI FILTERS
if has_ai:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 AI Filters")
    
    show_excellent_only = st.sidebar.checkbox("⭐ Excellent & Very Good Only")
    min_score = st.sidebar.slider("Min Deal Score", 0, 100, 0)
    hide_anomalies = st.sidebar.checkbox("🚫 Hide Anomalies")

# === APPLY FILTERS ===

df_filtered = df_current.copy()

if search_term:
    df_filtered = df_filtered[df_filtered['Item'].str.contains(search_term, case=False, na=False)]

if selected_store != 'All Stores':
    df_filtered = df_filtered[df_filtered['Store'] == selected_store]

if selected_category != 'All Categories':
    df_filtered = df_filtered[df_filtered['display_category'] == selected_category]
    
    if selected_subcategory != 'All Subcategories':
        df_filtered = df_filtered[df_filtered['display_subcategory'] == selected_subcategory]

df_filtered = df_filtered[(df_filtered['Price_Value'] >= min_price) & (df_filtered['Price_Value'] <= max_price)]

if has_ai:
    # v3.2: ai_deal_rating values are emoji strings now ("🔥 Hot Deal",
    # "✅ Good Deal", "😐 Fair", "⚠️ Below Average", "❌ Poor"), not the
    # legacy 'excellent'/'very_good' strings. Filter on the score column
    # which is more stable than rating-string matching.
    if show_excellent_only:
        df_filtered = df_filtered[df_filtered['ai_deal_score'] >= 70]

    df_filtered = df_filtered[df_filtered['ai_deal_score'] >= min_score]

    # ai_has_anomaly was removed in v3.x; hide_anomalies is now a no-op
    # but we keep the toggle so saved filter state doesn't error.

# === METRICS ===

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📦 Deals Found", f"{len(df_filtered):,}")

with col2:
    avg_price = df_filtered['Price_Value'].mean() if len(df_filtered) > 0 else 0
    st.metric("💰 Avg Price", f"${avg_price:.2f}" if avg_price > 0 else "N/A")

with col3:
    if has_ai and len(df_filtered) > 0:
        # v3.2: switched from rating-string matching to score threshold (>=70)
        # since ai_deal_rating no longer uses 'excellent'/'very_good'.
        top_deals = (df_filtered['ai_deal_score'] >= 70).sum()
        st.metric("⭐ Top Deals", top_deals)
    else:
        unique = df_filtered['Item'].nunique() if len(df_filtered) > 0 else 0
        st.metric("🏷️ Unique Items", unique)

with col4:
    if has_ai and len(df_filtered) > 0:
        avg_score = df_filtered['ai_deal_score'].mean()
        st.metric("📊 Avg Score", f"{avg_score:.0f}/100")
    else:
        stores_count = df_filtered['Store'].nunique() if len(df_filtered) > 0 else 0
        st.metric("🏪 Stores", stores_count)

st.markdown("---")

# === TABS ===

tab1, tab2, tab3 = st.tabs(["🏆 Best by Store", "📋 All Deals", "📊 Analytics"])

# === TAB 1: BEST DEALS BY STORE ===

with tab1:
    st.subheader("🏆 Top Deals from Each Store")
    
    if len(df_filtered) == 0:
        st.info("🔍 No deals match your filters.")
    else:
        top_n = st.slider("Deals per store", 3, 10, 5)
        
        # v3.2: removed duplicate sort_by_store radio block. The earlier
        # variant didn't include "Flyer Order" and Streamlit raises
        # DuplicateWidgetID when two radios share the same label.
        if has_ai:
            sort_by_store = st.radio(
                "Sort deals by",
                ["🏆 Best AI Score", "💰 Lowest Price", "💸 Highest Price", "📄 Flyer Order"],
                horizontal=True
            )
            
            if sort_by_store == "🏆 Best AI Score":
                sort_col, sort_asc = 'ai_deal_score', False
            elif sort_by_store == "💰 Lowest Price":
                sort_col, sort_asc = 'Price_Value', True
            elif sort_by_store == "💸 Highest Price":
                sort_col, sort_asc = 'Price_Value', False
            else:  # Flyer Order
                # Use Flyer_Order column if available, else use index
                if 'Flyer_Order' in df_filtered.columns:
                    sort_col, sort_asc = 'Flyer_Order', True
                else:
                    sort_col, sort_asc = None, None
        else:
            sort_by_store = st.radio(
                "Sort deals by", 
                ["💰 Lowest Price", "💸 Highest Price", "📄 Flyer Order"], 
                horizontal=True
            )
            if sort_by_store == "💰 Lowest Price":
                sort_col, sort_asc = 'Price_Value', True
            elif sort_by_store == "💸 Highest Price":
                sort_col, sort_asc = 'Price_Value', False
            else:
                if 'Flyer_Order' in df_filtered.columns:
                    sort_col, sort_asc = 'Flyer_Order', True
                else:
                    sort_col, sort_asc = None, None
        
        # Get best deals per store
        for store in sorted(df_filtered['Store'].unique()):
            store_deals = df_filtered[df_filtered['Store'] == store].copy()
            
            # Sort if requested
            if sort_col is not None:
                store_deals = store_deals.sort_values(sort_col, ascending=sort_asc)
            # else: keep original DataFrame order
            
            store_deals = store_deals.head(top_n)
            
            with st.expander(f"🏪 **{store}** ({len(store_deals)} deals)", expanded=True):
                for idx, row in store_deals.iterrows():
                    display_deal_card(row, f"{store}_{idx}", has_ai, load_historical_data())

# === TAB 2: ALL DEALS ===

with tab2:
    st.subheader("📋 Browse All Deals")
    
    if len(df_filtered) == 0:
        st.info("🔍 No deals match your filters.")
    else:
        col_sort, col_view = st.columns([2, 1])
        
        with col_sort:
            if has_ai:
                all_sorts = {
                    "🏆 AI Score: High → Low": ('ai_deal_score', False),
                    "💰 Price: Low → High": ('Price_Value', True),
                    "💰 Price: High → Low": ('Price_Value', False),
                    "🔤 Name: A → Z": ('Item', True),
                    "🏪 Store: A → Z": ('Store', True),
                    "📄 Flyer Order": ('Flyer_Order', True) if 'Flyer_Order' in df_filtered.columns else (None, None),
                }
            else:
                all_sorts = {
                    "💰 Price: Low → High": ('Price_Value', True),
                    "💰 Price: High → Low": ('Price_Value', False),
                    "🔤 Name: A → Z": ('Item', True),
                    "🏪 Store: A → Z": ('Store', True),
                    "📄 Flyer Order": ('Flyer_Order', True) if 'Flyer_Order' in df_filtered.columns else (None, None),
                }
            
            selected_all_sort = st.selectbox("Sort by", list(all_sorts.keys()))
            all_sort_col, all_sort_asc = all_sorts[selected_all_sort]
        
        with col_view:
            items_per_page = st.selectbox("Show", [25, 50, 100], index=1)
        
        # Apply sorting
        if all_sort_col is not None:
            df_display = df_filtered.sort_values(all_sort_col, ascending=all_sort_asc)
        else:
            df_display = df_filtered  # Keep original order
        
        for idx, row in df_display.head(items_per_page).iterrows():
            display_deal_card(row, f"all_{idx}", has_ai, load_historical_data())
        
        if len(df_display) > items_per_page:
            st.info(f"📋 Showing {items_per_page} of {len(df_display):,} deals.")

# === TAB 3: ANALYTICS ===

with tab3:
    if len(df_filtered) == 0:
        st.info("🔍 No data to analyze.")
    else:
        st.subheader("📊 Deal Analytics")
        
        chart_cols = st.columns(2)
        
        with chart_cols[0]:
            cat_counts = df_filtered['display_category'].value_counts().head(10)
            
            fig1 = px.bar(
                x=cat_counts.values, y=cat_counts.index, orientation='h',
                title="Top 10 Categories", labels={'x': 'Deals', 'y': 'Category'}
            )
            fig1.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)
        
        with chart_cols[1]:
            store_counts = df_filtered['Store'].value_counts()
            
            fig2 = px.pie(
                values=store_counts.values, names=store_counts.index,
                title="Deals by Store", hole=0.4
            )
            fig2.update_layout(height=400)
            st.plotly_chart(fig2, use_container_width=True)
        
        if has_ai:
            st.markdown("---")
            st.subheader("🤖 AI Quality Insights")
            
            ai_cols = st.columns(2)
            
            with ai_cols[0]:
                rating_counts = df_filtered['ai_deal_rating'].value_counts()
                
                fig3 = px.pie(
                    values=rating_counts.values, names=rating_counts.index,
                    title="Deal Quality Distribution"
                )
                st.plotly_chart(fig3, use_container_width=True)
            
            with ai_cols[1]:
                top10 = df_filtered.nlargest(10, 'ai_deal_score')[['Item', 'Store', 'Price_Value', 'ai_deal_score']]
                
                st.markdown("**🏆 Top 10 Rated Deals:**")
                st.dataframe(
                    top10,
                    column_config={
                        "Item": "Item",
                        "Store": "Store",
                        "Price_Value": st.column_config.NumberColumn("Price", format="$%.2f"),
                        "ai_deal_score": st.column_config.NumberColumn("Score", format="%d/100")
                    },
                    hide_index=True, use_container_width=True
                )

# === FOOTER ===

st.markdown("---")
footer_cols = st.columns(3)

with footer_cols[0]:
    st.caption(f"📅 {datetime.now().strftime('%b %d, %Y at %I:%M %p')}")

with footer_cols[1]:
    st.caption(f"📊 {len(df_filtered):,} of {len(df_current):,} deals")

with footer_cols[2]:
    st.caption("🤖 Powered by Claude" if has_ai else "💡 Run scraper for AI")
