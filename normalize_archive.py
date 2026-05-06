"""
Normalize historical archive — deduplicate ai_normalized_name values.

Problem: The AI normalizer gives slightly different names across scraper runs
(e.g., "Ground Beef (Regular)" vs "Regular Ground Beef" vs "Ground Beef").
This fragments price history and weakens deal scoring.

Strategy:
  1. For identical Item text: use the most recent ai_normalized_name
  2. Build keyword-similarity clusters to merge near-duplicates
  3. Within each cluster, pick the canonical name (most frequent)
  4. Write cleaned archive back to CSV

Run:  python normalize_archive.py
"""

import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from pathlib import Path

ARCHIVE_FILE = Path(__file__).parent / "historical_archive.csv"
BACKUP_FILE = Path(__file__).parent / "historical_archive_backup.csv"


def keyword_set(text: str) -> frozenset:
    """Extract meaningful keywords from a product name."""
    skip = {
        "fresh", "the", "and", "for", "with", "size", "family", "premium",
        "great", "value", "brand", "name", "new", "original", "pack",
        "selected", "varieties", "assorted", "flavours", "flavors",
    }
    words = str(text).lower().replace("(", " ").replace(")", " ").replace(",", " ").split()
    return frozenset(w for w in words if len(w) >= 3 and w not in skip)


def similarity(kw_a: frozenset, kw_b: frozenset) -> float:
    """Jaccard similarity: intersection / union. Prevents small-set false matches."""
    if not kw_a or not kw_b:
        return 0.0
    overlap = len(kw_a & kw_b)
    return overlap / len(kw_a | kw_b)


def build_name_clusters(norm_names: list[str], threshold: float = 0.65) -> dict[str, str]:
    """
    Cluster normalized names by keyword similarity.
    Returns a mapping: original_name -> canonical_name.
    """
    # Count frequency of each name
    freq = Counter(norm_names)
    unique_names = list(freq.keys())

    # Pre-compute keyword sets
    kw_map = {name: keyword_set(name) for name in unique_names}

    # Union-Find for clustering
    parent = {n: n for n in unique_names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # More frequent name becomes root
            if freq[ra] >= freq[rb]:
                parent[rb] = ra
            else:
                parent[ra] = rb

    # Compare pairs — only within same first-word groups for performance
    by_first_word = defaultdict(list)
    for name in unique_names:
        kws = kw_map[name]
        for w in kws:
            by_first_word[w].append(name)

    compared = set()
    for word, names in by_first_word.items():
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pair = (min(a, b), max(a, b))
                if pair in compared:
                    continue
                compared.add(pair)
                # Require at least 2 overlapping keywords to prevent false merges
                overlap = len(kw_map[a] & kw_map[b])
                if overlap < 2:
                    continue
                sim = similarity(kw_map[a], kw_map[b])
                if sim >= threshold:
                    union(a, b)

    # Build mapping: each name -> most frequent name in its cluster
    clusters = defaultdict(list)
    for name in unique_names:
        clusters[find(name)].append(name)

    mapping = {}
    for root, members in clusters.items():
        # Pick the most frequent member as canonical
        canonical = max(members, key=lambda n: freq[n])
        for m in members:
            if m != canonical:
                mapping[m] = canonical

    return mapping


def normalize_archive():
    if not ARCHIVE_FILE.exists():
        print("No historical archive found.")
        return

    df = pd.read_csv(ARCHIVE_FILE, low_memory=False)
    original_len = len(df)
    print(f"Loaded {original_len:,} rows")
    print(f"Unique ai_normalized_name before: {df['ai_normalized_name'].nunique()}")

    # Step 1: For identical Item text, fill missing normalized names
    # using the most recent non-null value
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    item_latest_norm = (
        df[df['ai_normalized_name'].notna()]
        .sort_values('Date')
        .drop_duplicates('Item', keep='last')
        .set_index('Item')['ai_normalized_name']
        .to_dict()
    )
    missing_before = df['ai_normalized_name'].isna().sum()
    df['ai_normalized_name'] = df.apply(
        lambda r: item_latest_norm.get(r['Item'], r['ai_normalized_name'])
        if pd.isna(r['ai_normalized_name']) else r['ai_normalized_name'],
        axis=1
    )
    missing_after = df['ai_normalized_name'].isna().sum()
    print(f"Filled {missing_before - missing_after} missing normalized names from Item lookup")

    # Step 2: For identical Items with DIFFERENT normalized names,
    # standardize to the most recent one
    for item, norm_name in item_latest_norm.items():
        mask = df['Item'] == item
        df.loc[mask, 'ai_normalized_name'] = norm_name
    print(f"Unique ai_normalized_name after Item-based standardization: {df['ai_normalized_name'].nunique()}")

    # Step 3: Keyword-similarity clustering to merge near-duplicates
    all_norms = df['ai_normalized_name'].dropna().tolist()
    mapping = build_name_clusters(all_norms, threshold=0.75)
    print(f"Keyword clustering merged {len(mapping)} name variants")

    if mapping:
        df['ai_normalized_name'] = df['ai_normalized_name'].map(
            lambda x: mapping.get(x, x)
        )

    # Also standardize ai_category and ai_sub_category using same Item->latest logic
    for col in ['ai_category', 'ai_sub_category']:
        if col in df.columns:
            item_latest = (
                df[df[col].notna()]
                .sort_values('Date')
                .drop_duplicates('Item', keep='last')
                .set_index('Item')[col]
                .to_dict()
            )
            for item, val in item_latest.items():
                mask = df['Item'] == item
                df.loc[mask, col] = val

    print(f"Unique ai_normalized_name final: {df['ai_normalized_name'].nunique()}")

    # Backup original
    import shutil
    shutil.copy2(ARCHIVE_FILE, BACKUP_FILE)
    print(f"Backup saved to {BACKUP_FILE}")

    # Write cleaned archive
    df.to_csv(ARCHIVE_FILE, index=False)
    print(f"Saved normalized archive: {len(df):,} rows")

    # Summary stats
    print("\n--- Summary ---")
    print(f"Rows: {original_len:,}")
    print(f"Names merged by clustering: {len(mapping)}")
    print(f"Missing names filled: {missing_before - missing_after}")


if __name__ == "__main__":
    normalize_archive()
