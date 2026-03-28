"""
Calgary Grocery Hub — Data Layer
Loads CSVs, caches in memory, pre-computes insights.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path(__file__).parent.parent
CURRENT_FILE = DATA_DIR / "current_flyers.csv"
HISTORICAL_FILE = DATA_DIR / "historical_archive.csv"

PROTEIN_CATEGORIES = ["Beef", "Pork", "Poultry", "Lamb", "Seafood"]


def to_python(val):
    """Convert numpy/pandas types to native Python for JSON serialization."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, pd.Timestamp):
        return str(val)
    return val


class DataStore:
    def __init__(self):
        self.current: pd.DataFrame = pd.DataFrame()
        self.historical: pd.DataFrame = pd.DataFrame()
        self.insights: dict = {}
        self.loaded_at: datetime | None = None
        self._file_mtimes: dict[str, float] = {}

    def _get_file_mtimes(self) -> dict[str, float]:
        mtimes = {}
        for f in [CURRENT_FILE, HISTORICAL_FILE]:
            if f.exists():
                mtimes[str(f)] = f.stat().st_mtime
        return mtimes

    def check_reload(self):
        """Reload data if CSV files have changed on disk."""
        current_mtimes = self._get_file_mtimes()
        if current_mtimes != self._file_mtimes:
            self.load()

    def load(self):
        # Current flyers
        if CURRENT_FILE.exists():
            self.current = pd.read_csv(CURRENT_FILE, low_memory=False)
            self._coerce_current()
        # Historical archive
        if HISTORICAL_FILE.exists():
            self.historical = pd.read_csv(HISTORICAL_FILE, low_memory=False)
            self.historical["Date"] = pd.to_datetime(
                self.historical["Date"], errors="coerce"
            )
            self.historical = self.historical.dropna(subset=["Date"])
        self.insights = self._compute_insights()
        self.loaded_at = datetime.now()
        self._file_mtimes = self._get_file_mtimes()

    def _coerce_current(self):
        df = self.current
        num_cols = [
            "Price_Value", "deal_score", "ai_deal_score",
            "historical_min", "historical_max", "historical_avg",
            "historical_count", "price_percentile", "pct_below_avg",
            "cross_store_rank", "cross_store_count", "unit_price",
        ]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        bool_cols = ["is_lowest_historical", "is_kvi"]
        for c in bool_cols:
            if c in df.columns:
                df[c] = df[c].fillna(False).astype(bool)
        if "ai_category" in df.columns:
            df["ai_category"] = df["ai_category"].fillna("Other")
        if "deal_score" in df.columns:
            df["deal_score"] = df["deal_score"].fillna(0)

    def _compute_insights(self) -> dict:
        df = self.current
        if df.empty:
            return {"total_deals": 0}

        lowest_ever = int(df["is_lowest_historical"].sum()) if "is_lowest_historical" in df.columns else 0
        hot_count = int((df["deal_score"] >= 80).sum()) if "deal_score" in df.columns else 0
        kvi_count = int(df["is_kvi"].sum()) if "is_kvi" in df.columns else 0

        # Best store by avg deal_score
        best_store = {"name": "N/A", "avg_score": 0, "deal_count": 0}
        if "deal_score" in df.columns:
            store_scores = df.groupby("Store")["deal_score"].agg(["mean", "count"])
            if len(store_scores) > 0:
                best = store_scores["mean"].idxmax()
                best_store = {
                    "name": best,
                    "avg_score": round(float(store_scores.loc[best, "mean"]), 1),
                    "deal_count": int(store_scores.loc[best, "count"]),
                }

        # Top 5 deals
        top5 = []
        if "deal_score" in df.columns:
            top = df.nlargest(5, "deal_score")
            for idx, row in top.iterrows():
                top5.append(self._deal_to_dict(row, int(idx)))

        # Category counts
        cat_counts = {}
        if "ai_category" in df.columns:
            cat_counts = df["ai_category"].value_counts().to_dict()

        # Store counts
        store_counts = df["Store"].value_counts().to_dict()

        # Date range
        valid_from = None
        valid_until = None
        if "Valid_From" in df.columns:
            vf = pd.to_datetime(df["Valid_From"], errors="coerce")
            valid_from = str(vf.min()) if vf.notna().any() else None
        if "Valid_Until" in df.columns:
            vu = pd.to_datetime(df["Valid_Until"], errors="coerce")
            valid_until = str(vu.max()) if vu.notna().any() else None

        return {
            "total_deals": len(df),
            "lowest_ever_count": lowest_ever,
            "hot_deal_count": hot_count,
            "kvi_on_sale": kvi_count,
            "avg_score": round(float(df["deal_score"].mean()), 1) if "deal_score" in df.columns else 0,
            "best_store": best_store,
            "top_5_deals": top5,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "category_counts": cat_counts,
            "store_counts": store_counts,
        }

    def _deal_to_dict(self, row, idx: int) -> dict:
        """Convert a DataFrame row to a deal dict for API responses."""
        def safe(col, default=None):
            v = row.get(col, default)
            if v is None:
                return default
            try:
                if pd.isna(v):
                    return default
            except (TypeError, ValueError):
                pass
            return to_python(v)

        tags = self._compute_tags(row)

        return {
            "id": idx,
            "item": safe("Item", ""),
            "store": safe("Store", ""),
            "price": safe("Price_Value", 0),
            "price_text": safe("Price_Text", ""),
            "price_basis": safe("price_basis", "each"),
            "unit_price": safe("unit_price"),
            "unit_type": safe("unit_type"),
            "deal_score": safe("deal_score", 0),
            "ai_deal_score": safe("ai_deal_score", 0),
            "ai_deal_rating": safe("ai_deal_rating", ""),
            "ai_explanation": safe("ai_explanation", ""),
            "category": safe("ai_category", "Other"),
            "sub_category": safe("ai_sub_category", ""),
            "brand": safe("ai_brand"),
            "normalized_name": safe("ai_normalized_name", ""),
            "is_lowest_historical": bool(safe("is_lowest_historical", False)),
            "pct_below_avg": safe("pct_below_avg", 0),
            "historical_min": safe("historical_min"),
            "historical_max": safe("historical_max"),
            "historical_avg": safe("historical_avg"),
            "historical_count": safe("historical_count", 0),
            "price_percentile": safe("price_percentile"),
            "cross_store_rank": safe("cross_store_rank"),
            "cross_store_count": safe("cross_store_count", 0),
            "is_kvi": bool(safe("is_kvi", False)),
            "tags": tags,
        }

    def _compute_tags(self, row) -> list[str]:
        tags = []
        if row.get("is_lowest_historical", False):
            tags.append("LOWEST EVER")
        pct = row.get("pct_below_avg", 0)
        if pd.notna(pct) and isinstance(pct, (int, float)) and pct > 10:
            tags.append(f"{int(pct)}% below avg")
        rank = row.get("cross_store_rank")
        count = row.get("cross_store_count", 0)
        if pd.notna(rank) and rank == 1 and pd.notna(count) and count > 1:
            tags.append(f"Best of {int(count)} stores")
        if row.get("is_kvi", False):
            tags.append("Staple")
        score = row.get("deal_score", 0)
        if pd.notna(score) and score >= 80:
            tags.append("Hot Deal")
        return tags

    # --- Query methods ---

    def get_deals(
        self,
        category: str | None = None,
        store: str | None = None,
        search: str | None = None,
        preset: str | None = None,
        min_score: int | None = None,
        sort: str = "score_desc",
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict], int]:
        df = self.current.copy()
        if df.empty:
            return [], 0

        # Preset filters
        if preset == "lowest_ever":
            df = df[df["is_lowest_historical"] == True]
        elif preset == "hot_deals":
            df = df[df["deal_score"] >= 80]
        elif preset == "best_protein":
            df = df[df["ai_category"].isin(PROTEIN_CATEGORIES)]
        elif preset == "under_5":
            df = df[df["Price_Value"] < 5.0]
        elif preset == "staples":
            df = df[df["is_kvi"] == True]

        # Filters
        if category:
            df = df[df["ai_category"] == category]
        if store:
            df = df[df["Store"] == store]
        if search:
            term = search.lower()
            mask = df["Item"].str.lower().str.contains(term, na=False)
            if "ai_normalized_name" in df.columns:
                mask |= df["ai_normalized_name"].str.lower().str.contains(term, na=False)
            if "ai_brand" in df.columns:
                mask |= df["ai_brand"].fillna("").str.lower().str.contains(term, na=False)
            df = df[mask]
        if min_score is not None:
            df = df[df["deal_score"] >= min_score]

        total = len(df)

        # Sort
        sort_map = {
            "score_desc": ("deal_score", False),
            "score_asc": ("deal_score", True),
            "price_asc": ("Price_Value", True),
            "price_desc": ("Price_Value", False),
            "pct_below_desc": ("pct_below_avg", False),
            "name_asc": ("Item", True),
        }
        col, asc = sort_map.get(sort, ("deal_score", False))
        df = df.sort_values(col, ascending=asc, na_position="last")

        # Paginate
        page = df.iloc[offset: offset + limit]
        deals = [self._deal_to_dict(row, int(idx)) for idx, row in page.iterrows()]
        return deals, total

    def get_deal(self, deal_id: int) -> dict | None:
        if deal_id not in self.current.index:
            return None
        row = self.current.loc[deal_id]
        return self._deal_to_dict(row, deal_id)

    def get_deal_history(self, deal_id: int) -> dict | None:
        if deal_id not in self.current.index:
            return None

        row = self.current.loc[deal_id]
        deal = self._deal_to_dict(row, deal_id)

        # Find historical matches via ai_normalized_name + fuzzy fallback
        norm_name = row.get("ai_normalized_name")
        history_records = []
        if not self.historical.empty:
            matches = pd.DataFrame()

            # 1) Exact normalized name match
            if pd.notna(norm_name) and str(norm_name).strip():
                matches = self.historical[
                    self.historical["ai_normalized_name"] == norm_name
                ]

            # 2) Fallback: keyword overlap on normalized names + item names
            if len(matches) < 3:
                # Build keyword set from both normalized name and item name
                item_str = str(row.get("Item", "")).lower()
                norm_str = str(norm_name).lower() if pd.notna(norm_name) else ""
                combined = f"{item_str} {norm_str}"
                # Extract meaningful keywords (3+ chars, skip filler)
                skip = {"fresh", "the", "and", "for", "with", "size", "family", "premium"}
                keywords = {w for w in combined.split() if len(w) >= 3 and w not in skip}

                if keywords:
                    hist_items = self.historical["Item"].str.lower().fillna("")
                    hist_norms = self.historical["ai_normalized_name"].str.lower().fillna("")
                    hist_combined = hist_items + " " + hist_norms

                    # Score each historical row by keyword overlap
                    def keyword_score(text):
                        return sum(1 for kw in keywords if kw in text)

                    scores = hist_combined.apply(keyword_score)
                    # Require at least 60% keyword overlap
                    threshold = max(2, int(len(keywords) * 0.6))
                    fuzzy_matches = self.historical[scores >= threshold]

                    if len(fuzzy_matches) > len(matches):
                        matches = fuzzy_matches
            matches = matches.sort_values("Date")
            for _, h in matches.iterrows():
                history_records.append({
                    "date": str(h["Date"].date()) if pd.notna(h["Date"]) else None,
                    "price": float(h["Price_Value"]) if pd.notna(h.get("Price_Value")) else None,
                    "store": str(h.get("Store", "")),
                })

        # Cross-store prices (this week)
        cross_store = []
        if pd.notna(norm_name) and str(norm_name).strip():
            same = self.current[self.current["ai_normalized_name"] == norm_name]
            same = same.sort_values("Price_Value")
            for rank, (_, s) in enumerate(same.iterrows(), 1):
                cross_store.append({
                    "store": str(s["Store"]),
                    "price": float(s["Price_Value"]),
                    "rank": rank,
                })

        # Stats
        hist_min = deal.get("historical_min")
        hist_avg = deal.get("historical_avg")
        hist_count = deal.get("historical_count", 0)

        # Last on sale
        last_on_sale = None
        freq = None
        if history_records:
            today = datetime.now().date()
            past = [h for h in history_records if h["date"] and h["date"] < str(today)]
            if past:
                last = past[-1]
                last_on_sale = last

            if len(history_records) >= 2:
                dates = [h["date"] for h in history_records if h["date"]]
                if len(dates) >= 2:
                    first = datetime.strptime(dates[0], "%Y-%m-%d")
                    latest = datetime.strptime(dates[-1], "%Y-%m-%d")
                    span_months = max((latest - first).days / 30, 1)
                    freq = round(len(dates) / span_months, 1)

        return {
            "deal": deal,
            "price_history": history_records,
            "cross_store_prices": cross_store,
            "stats": {
                "historical_min": to_python(hist_min),
                "historical_max": to_python(deal.get("historical_max")),
                "historical_avg": to_python(hist_avg),
                "historical_count": int(hist_count) if hist_count and not pd.isna(hist_count) else 0,
                "price_percentile": to_python(deal.get("price_percentile")),
                "last_on_sale": last_on_sale,
                "sale_frequency_per_month": freq,
            },
            "ai_explanation": deal.get("ai_explanation", ""),
        }

    def get_stores(self) -> list[dict]:
        df = self.current
        if df.empty:
            return []

        stores = []
        store_groups = df.groupby("Store")
        for name, group in store_groups:
            lowest = int(group["is_lowest_historical"].sum()) if "is_lowest_historical" in group.columns else 0
            pct_vals = group["pct_below_avg"].dropna()
            avg_savings = round(float(pct_vals[pct_vals > 0].mean()), 1) if len(pct_vals[pct_vals > 0]) > 0 else 0

            stores.append({
                "name": name,
                "deal_count": len(group),
                "avg_score": round(float(group["deal_score"].mean()), 1),
                "hot_deals": int((group["deal_score"] >= 80).sum()),
                "lowest_ever": lowest,
                "avg_savings": avg_savings,
            })

        stores.sort(key=lambda s: s["avg_score"], reverse=True)
        return stores

    def get_categories(self) -> list[dict]:
        df = self.current
        if df.empty or "ai_category" not in df.columns:
            return []

        cats = []
        for cat, group in df.groupby("ai_category"):
            cats.append({
                "name": cat,
                "count": len(group),
                "avg_score": round(float(group["deal_score"].mean()), 1),
            })
        cats.sort(key=lambda c: c["count"], reverse=True)
        return cats


store = DataStore()
