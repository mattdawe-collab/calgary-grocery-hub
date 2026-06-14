from datetime import datetime
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.data import store

router = APIRouter()


def _money(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _plain(value, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _split_bullets(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _stat_card(label: str, value: str) -> str:
    return f"""
      <div class="stat">
        <div class="stat-value">{escape(value)}</div>
        <div class="stat-label">{escape(label)}</div>
      </div>
    """


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    if value is None or value == "":
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _date_label(value) -> str:
    if value is None:
        return ""
    return value.strftime("%b %d").replace(" 0", " ")


def _price_history_chart(payload: dict) -> str:
    deal = payload["deal"]
    stats = payload.get("stats", {})
    current_price = _float_or_none(deal.get("price"))
    current_date = _parse_date(deal.get("valid_from")) or datetime.now().date()
    by_date: dict = {}

    for row in payload.get("price_history", []):
        observed_date = _parse_date(row.get("date"))
        observed_price = _float_or_none(row.get("price"))
        if observed_date is None or observed_price is None:
            continue
        previous = by_date.get(observed_date)
        by_date[observed_date] = observed_price if previous is None else min(previous, observed_price)

    if current_price is not None:
        by_date[current_date] = current_price

    points = sorted(by_date.items())
    if len(points) > 24:
        points = points[-24:]

    if not points:
        return """
      <section class="chart-card" aria-labelledby="price-history-title">
        <div class="chart-head">
          <div>
            <h2 id="price-history-title">Price history</h2>
            <p>No price-history observations are available for this item yet.</p>
          </div>
        </div>
      </section>
        """

    prices = [price for _, price in points]
    avg_price = _float_or_none(stats.get("historical_avg"))
    scale_prices = prices + ([avg_price] if avg_price is not None else [])
    min_price = min(scale_prices)
    max_price = max(scale_prices)
    if min_price == max_price:
        pad = max(min_price * 0.12, 0.5)
        min_price -= pad
        max_price += pad
    else:
        pad = (max_price - min_price) * 0.14
        min_price = max(0, min_price - pad)
        max_price += pad

    width = 640
    height = 220
    left = 52
    right = 22
    top = 22
    bottom = 42
    plot_width = width - left - right
    plot_height = height - top - bottom

    def x_at(idx: int) -> float:
        if len(points) == 1:
            return left + plot_width / 2
        return left + (plot_width * idx / (len(points) - 1))

    def y_at(price: float) -> float:
        return top + ((max_price - price) / (max_price - min_price) * plot_height)

    coords = [(x_at(idx), y_at(price), date, price) for idx, (date, price) in enumerate(points)]
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in coords)
    circles = "\n".join(
        f'<circle class="chart-dot" cx="{x:.1f}" cy="{y:.1f}" r="3.3"><title>{escape(_date_label(date))}: {escape(_money(price))}</title></circle>'
        for x, y, date, price in coords
    )

    current_idx = next(
        (idx for idx, (_, _, date, price) in enumerate(coords) if date == current_date and price == current_price),
        len(coords) - 1,
    )
    current_x, current_y, _, current_value = coords[current_idx]
    current_label_y = max(16, current_y - 10)
    current_anchor = "end" if current_x > width - 120 else "start"
    current_text_x = current_x - 8 if current_anchor == "end" else current_x + 8

    avg_line = ""
    if avg_price is not None:
        avg_y = y_at(avg_price)
        avg_line = f"""
        <line class="chart-avg" x1="{left}" x2="{width - right}" y1="{avg_y:.1f}" y2="{avg_y:.1f}"></line>
        <text class="chart-avg-label" x="{width - right}" y="{max(12, avg_y - 5):.1f}" text-anchor="end">avg {escape(_money(avg_price))}</text>
        """

    line_or_point = (
        f'<polyline class="chart-line" points="{polyline}"></polyline>'
        if len(coords) > 1
        else ""
    )
    trend_note = (
        "Lowest observed flyer price by date. Current deal highlighted."
        if len(coords) > 1
        else "Not enough history for a trend yet. Current deal shown."
    )

    first_date = _date_label(points[0][0])
    last_date = _date_label(points[-1][0])
    current_badge = _money(current_value)

    return f"""
      <section class="chart-card" aria-labelledby="price-history-title">
        <div class="chart-head">
          <div>
            <h2 id="price-history-title">Price history</h2>
            <p>{escape(trend_note)}</p>
          </div>
          <span class="chart-now">Current {escape(current_badge)}</span>
        </div>
        <svg class="price-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="price-chart-title price-chart-desc">
          <title id="price-chart-title">Price history for {escape(_plain(deal.get("item"), "deal"))}</title>
          <desc id="price-chart-desc">Recent price observations from {escape(first_date)} to {escape(last_date)} with current price highlighted.</desc>
          <line class="chart-axis" x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}"></line>
          <line class="chart-axis" x1="{left}" x2="{left}" y1="{top}" y2="{height - bottom}"></line>
          <line class="chart-grid" x1="{left}" x2="{width - right}" y1="{top}" y2="{top}"></line>
          <line class="chart-grid" x1="{left}" x2="{width - right}" y1="{top + plot_height / 2:.1f}" y2="{top + plot_height / 2:.1f}"></line>
          {avg_line}
          {line_or_point}
          {circles}
          <circle class="chart-current" cx="{current_x:.1f}" cy="{current_y:.1f}" r="6"></circle>
          <text class="chart-current-label" x="{current_text_x:.1f}" y="{current_label_y:.1f}" text-anchor="{current_anchor}">Current {escape(_money(current_value))}</text>
          <text class="chart-tick" x="{left}" y="{height - 14}" text-anchor="start">{escape(first_date)}</text>
          <text class="chart-tick" x="{width - right}" y="{height - 14}" text-anchor="end">{escape(last_date)}</text>
          <text class="chart-tick" x="{left - 8}" y="{y_at(max(prices)) + 4:.1f}" text-anchor="end">{escape(_money(max(prices)))}</text>
          <text class="chart-tick" x="{left - 8}" y="{y_at(min(prices)) + 4:.1f}" text-anchor="end">{escape(_money(min(prices)))}</text>
        </svg>
      </section>
    """


def render_deal_snapshot_html(payload: dict, dashboard_url: str = "/") -> str:
    deal = payload["deal"]
    stats = payload.get("stats", {})
    cross_store = payload.get("cross_store_prices", [])
    why = _split_bullets(deal.get("why_bullets"))

    item = _plain(deal.get("item"), "Deal")
    price = _money(deal.get("price"))
    store_name = _plain(deal.get("store"))
    category = _plain(deal.get("category"))
    action = _plain(deal.get("action_label"), "Deal")
    score = round(float(deal.get("deal_score") or 0))
    confidence = round(float(deal.get("confidence_score") or 0))
    unit = ""
    if deal.get("unit_price") is not None and deal.get("unit_type"):
        unit = f"{_money(deal.get('unit_price'))} {deal.get('unit_type')}"

    rank_line = ""
    rank = deal.get("cross_store_rank")
    count = deal.get("cross_store_count")
    if rank and count and count > 1:
        rank_line = f"#{int(rank)} of {int(count)} stores this week"

    cross_rows = ""
    if cross_store:
        cross_rows = "".join(
            f"<li>{escape(_plain(row.get('store')))}: {escape(_money(row.get('price')))}</li>"
            for row in cross_store[:5]
        )
    else:
        cross_rows = "<li>No same-item store comparison available.</li>"

    why_rows = "".join(f"<li>{escape(text)}</li>" for text in why[:4]) or "<li>No evidence bullets available.</li>"
    title = f"{item} - {price} at {store_name}"
    description = f"{action}. Score {score}, confidence {confidence}. {category}."
    price_chart = _price_history_chart(payload)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta name="description" content="{escape(description)}">
  <style>
    body {{
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc;
      color: #0f172a;
    }}
    main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 24px;
    }}
    .panel {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 22px;
      box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }}
    .kicker {{
      font-size: 13px;
      color: #2563eb;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
      line-height: 1.15;
    }}
    .price {{
      font-size: 34px;
      font-weight: 800;
      color: #15803d;
      margin-right: 10px;
    }}
    .store {{
      color: #475569;
      font-size: 16px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0;
    }}
    .pill {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 13px;
      font-weight: 600;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin: 18px 0;
    }}
    .stat {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 12px;
      text-align: center;
    }}
    .stat-value {{
      font-size: 18px;
      font-weight: 800;
    }}
    .stat-label {{
      font-size: 12px;
      color: #64748b;
      margin-top: 3px;
    }}
    .chart-card {{
      background: #fbfdff;
      border: 1px solid #dbeafe;
      border-radius: 10px;
      padding: 14px;
      margin: 18px 0;
    }}
    .chart-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 8px;
    }}
    .chart-head h2 {{
      margin: 0 0 4px;
    }}
    .chart-head p {{
      margin: 0;
      color: #64748b;
      font-size: 13px;
      line-height: 1.35;
    }}
    .chart-now {{
      flex: 0 0 auto;
      color: #166534;
      background: #dcfce7;
      border: 1px solid #86efac;
      border-radius: 999px;
      padding: 6px 9px;
      font-size: 13px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .price-chart {{
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
    }}
    .chart-axis {{
      stroke: #94a3b8;
      stroke-width: 1.2;
    }}
    .chart-grid {{
      stroke: #e2e8f0;
      stroke-width: 1;
    }}
    .chart-avg {{
      stroke: #f59e0b;
      stroke-width: 1.4;
      stroke-dasharray: 5 5;
    }}
    .chart-line {{
      fill: none;
      stroke: #2563eb;
      stroke-width: 3;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .chart-dot {{
      fill: white;
      stroke: #2563eb;
      stroke-width: 2;
    }}
    .chart-current {{
      fill: #16a34a;
      stroke: white;
      stroke-width: 2.5;
    }}
    .chart-current-label {{
      fill: #14532d;
      font-size: 13px;
      font-weight: 800;
    }}
    .chart-avg-label,
    .chart-tick {{
      fill: #64748b;
      font-size: 12px;
    }}
    h2 {{
      font-size: 15px;
      margin: 20px 0 8px;
      color: #334155;
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
      color: #334155;
    }}
    li {{
      margin: 5px 0;
    }}
    .footer {{
      margin-top: 20px;
      color: #64748b;
      font-size: 13px;
    }}
    .footer a {{
      color: #2563eb;
      text-decoration: none;
      font-weight: 600;
    }}
    @media (max-width: 560px) {{
      main {{ padding: 14px; }}
      .panel {{ padding: 16px; border-radius: 10px; }}
      h1 {{ font-size: 23px; }}
      .price {{ font-size: 30px; display: block; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .chart-head {{ display: block; }}
      .chart-now {{ display: inline-block; margin-top: 8px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <div class="kicker">{escape(action)}</div>
      <h1>{escape(item)}</h1>
      <div>
        <span class="price">{escape(price)}</span>
        <span class="store">at {escape(store_name)}</span>
      </div>
      <div class="meta">
        <span class="pill">Score {score}</span>
        <span class="pill">Confidence {confidence}</span>
        <span class="pill">{escape(category)}</span>
        {f'<span class="pill">{escape(rank_line)}</span>' if rank_line else ''}
        {f'<span class="pill">{escape(unit)}</span>' if unit else ''}
      </div>
      <div class="stats">
        {_stat_card("Historical Low", _money(stats.get("historical_min")))}
        {_stat_card("Average", _money(stats.get("historical_avg")))}
        {_stat_card("Historical High", _money(stats.get("historical_max")))}
        {_stat_card("Times Seen", str(stats.get("historical_count") or 0))}
        {_stat_card("Percentile", f"{round(float(stats.get('price_percentile') or 0))}th" if stats.get("price_percentile") is not None else "N/A")}
        {_stat_card("Sales/Month", f"~{stats.get('sale_frequency_per_month')}x" if stats.get("sale_frequency_per_month") else "N/A")}
      </div>
      {price_chart}
      <h2>Why it made the list</h2>
      <ul>{why_rows}</ul>
      <h2>This week's store comparison</h2>
      <ul>{cross_rows}</ul>
      <div class="footer">
        Snapshot generated from Calgary Grocery Hub data.
        <a href="{escape(dashboard_url)}">Open dashboard</a>
      </div>
    </section>
  </main>
</body>
</html>"""


@router.get("/share/deals/{deal_id}", response_class=HTMLResponse)
def deal_snapshot(deal_id: int, request: Request):
    store.check_reload()
    payload = store.get_deal_history(deal_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return HTMLResponse(content=render_deal_snapshot_html(payload, str(request.base_url)))
