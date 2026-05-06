"""Quick check of Costco and Wholesale Club data from Flipp."""
import requests

BASE_URL = "https://backflipp.wishabi.com/flipp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/"
}

resp = requests.get(f"{BASE_URL}/flyers", params={"postal_code": "T3M1M9", "locale": "en-ca"}, headers=HEADERS)
flyers = resp.json().get("flyers", [])

for store_keyword, label in [("costco", "COSTCO"), ("wholesale", "WHOLESALE CLUB")]:
    print(f"\n{'='*60}")
    print(f" {label}")
    print(f"{'='*60}")

    for f in flyers:
        m = f.get("merchant", "").lower()
        if store_keyword not in m:
            continue

        flyer_id = f["id"]
        name = f.get("name", "")
        print(f"\nFlyer: {name} (ID: {flyer_id})")
        print(f"Valid: {f.get('valid_from')} - {f.get('valid_to')}")

        items_resp = requests.get(f"{BASE_URL}/flyers/{flyer_id}", headers=HEADERS)
        data = items_resp.json()
        items = data.get("items") or data.get("spread_items") or []
        print(f"Items: {len(items)}")

        # Show sample items
        grocery_count = 0
        non_grocery = 0
        for item in items[:20]:
            name_str = item.get("name", "")
            price = item.get("current_price", "?")
            price_text = item.get("price_text", "")
            pre_price = item.get("pre_price_text", "")
            print(f"  {name_str[:55]:55} ${price:>8} | {pre_price} {price_text}")

        print(f"  ... ({len(items)} total)")
        break  # Just first flyer per store
