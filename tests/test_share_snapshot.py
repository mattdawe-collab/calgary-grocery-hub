from api.routes.share import render_deal_snapshot_html


def test_snapshot_includes_price_history_chart():
    payload = {
        "deal": {
            "id": 1,
            "item": "Chicken Breast",
            "store": "Test Market",
            "price": 4.99,
            "category": "Poultry",
            "action_label": "Stock up",
            "deal_score": 94,
            "confidence_score": 88,
            "valid_from": "2026-06-12",
            "why_bullets": ["Below average price"],
        },
        "stats": {
            "historical_min": 4.99,
            "historical_avg": 6.49,
            "historical_max": 8.99,
            "historical_count": 3,
            "price_percentile": 8,
        },
        "price_history": [
            {"date": "2026-04-01", "price": 8.99, "store": "Test Market"},
            {"date": "2026-05-01", "price": 6.49, "store": "Test Market"},
        ],
        "cross_store_prices": [],
    }

    html = render_deal_snapshot_html(payload, "https://example.com/")

    assert "Price history" in html
    assert '<svg class="price-chart"' in html
    assert "Current $4.99" in html
    assert "avg $6.49" in html
