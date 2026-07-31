"""Generate a static dashboard from the committed history. Served by GitHub Pages."""
import json
import os
from datetime import datetime, timezone

import analyze

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "index.html")

TPL = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Price Sentinel</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e8eaed;margin:0;padding:24px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#8b93a1;font-size:13px;margin-bottom:24px}
 .grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
 .card{background:#181b21;border:1px solid #262b35;border-radius:12px;padding:16px}
 .card.hit{border-color:#2ea043;box-shadow:0 0 0 1px #2ea04340}
 .name{font-size:14px;font-weight:600;margin-bottom:8px;line-height:1.35}
 .name a{color:#e8eaed;text-decoration:none} .name a:hover{color:#58a6ff}
 .price{font-size:26px;font-weight:700} .price.hit{color:#3fb950}
 .meta{color:#8b93a1;font-size:12px;margin:6px 0 12px}
 .badge{display:inline-block;background:#2ea043;color:#fff;font-size:11px;
   padding:2px 8px;border-radius:10px;margin-left:8px;vertical-align:middle}
 canvas{max-height:120px}
</style></head><body>
<h1>Price Sentinel</h1><div class="sub">Updated __TS__ UTC &middot; __N__ tracked</div>
<div class="grid">__CARDS__</div>
<script>__SCRIPTS__</script></body></html>"""


def build(products, state):
    cards, scripts = [], []
    for i, p in enumerate(products):
        asin = p["asin"]
        hist = analyze.load_history(asin, days=180)
        if not hist:
            continue
        rec = state.get(asin, {})
        price = hist[-1][1]
        prices = sorted(x[1] for x in hist)
        lo, med = prices[0], analyze.percentile(prices, 50)
        score = rec.get("last_score", 0)
        hit = score >= 60
        labels = json.dumps([t.strftime("%d %b") for t, _ in hist])
        series = json.dumps([round(v, 2) for _, v in hist])
        name = (p.get("name") or asin)[:70]
        url = p.get("url") or f"https://www.amazon.in/dp/{asin}"

        cards.append(
            f'<div class="card{" hit" if hit else ""}">'
            f'<div class="name"><a href="{url}" target="_blank">{name}</a>'
            f'{"<span class=badge>BUY ZONE</span>" if hit else ""}</div>'
            f'<div class="price{" hit" if hit else ""}">&#8377;{price:,.0f}</div>'
            f'<div class="meta">180d low &#8377;{lo:,.0f} &middot; median &#8377;{med:,.0f} '
            f'&middot; score {score}/100</div>'
            f'<canvas id="c{i}"></canvas></div>'
        )
        scripts.append(
            f"new Chart(document.getElementById('c{i}'),{{type:'line',"
            f"data:{{labels:{labels},datasets:[{{data:{series},borderColor:'"
            f"{'#3fb950' if hit else '#58a6ff'}',borderWidth:2,pointRadius:0,tension:.15,fill:false}}]}},"
            f"options:{{plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#6b7280',maxTicksLimit:4}},"
            f"grid:{{display:false}}}},y:{{ticks:{{color:'#6b7280',maxTicksLimit:4}},grid:{{color:'#262b35'}}}}}}}}}});"
        )

    html = (TPL.replace("__TS__", datetime.now(timezone.utc).strftime("%d %b %Y %H:%M"))
                .replace("__N__", str(len(cards)))
                .replace("__CARDS__", "".join(cards) or "<p>No data yet.</p>")
                .replace("__SCRIPTS__", "".join(scripts)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"[dashboard] wrote {OUT}")
