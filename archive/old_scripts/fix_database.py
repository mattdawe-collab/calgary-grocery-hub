import pandas as pd

# 1. Load Data
df = pd.read_csv("seton_grocery_history.csv")
print(f"Original Count: {len(df)}")

# 2. Sort to ensure the "Better" rows are on top
# We sort by Sub_Category so that 'NaN' values sink to the bottom
df = df.sort_values(by=['Date', 'Store', 'Item', 'Sub_Category'], na_position='last')

# 3. Drop Duplicates
# We keep the 'first' one (which is now the one with the Sub_Category)
subset_cols = ['Date', 'Store', 'Item', 'Price_Value']
df_clean = df.drop_duplicates(subset=subset_cols, keep='first')

# 4. Save
print(f"Cleaned Count: {len(df_clean)}")
print(f"Removed {len(df) - len(df_clean)} duplicates.")
df_clean.to_csv("clean_grocery_data.csv", index=False)