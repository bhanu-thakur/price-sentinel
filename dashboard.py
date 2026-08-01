"""Generate the static verdict-first dashboard and lazy chart data."""

import html
import json
import os
from datetime import datetime, timedelta, timezone

import analyze


ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "index.html")
CHART_DATA_DIR = os.path.join(ROOT, "docs", "chart-data")
RETAILER_LABELS = {
    "amazon.in": "Amazon",
    "flipkart.com": "Flipkart",
    "myntra.com": "Myntra",
    "croma.com": "Croma",
    "tatacliq.com": "Tata CLiQ",
    "ajio.com": "AJIO",
    "snapdeal.com": "Snapdeal",
    "reliancedigital.in": "Reliance Digital",
    "vijaysales.com": "Vijay Sales",
}


def daily_low(hist):
    """Collapse intra-day samples to one point per day."""
    by_day = {}
    for timestamp, price in hist:
        key = timestamp.date()
        if key not in by_day or price < by_day[key][1]:
            by_day[key] = (timestamp, price)
    return [by_day[key] for key in sorted(by_day)]


def provider_history(record):
    """Return validated provider chart points without mixing them into own history."""
    points = []
    for item in record.get("provider_history") or []:
        try:
            timestamp = datetime.fromisoformat(str(item["date"])[:10]).replace(tzinfo=timezone.utc)
            price = float(item["price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price > 0:
            points.append((timestamp, price))
    return daily_low(points)


def _escape(value, quote=False):
    return html.escape(str(value or ""), quote=quote)


def _group_inr(number):
    """Group digits en-IN: last three, then pairs. 1249900 -> 12,49,900."""
    digits = str(int(number))
    sign = ""
    if digits.startswith("-"):
        sign, digits = "-", digits[1:]
    if len(digits) <= 3:
        return sign + digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _money(value):
    if value is None:
        return "—"
    return f"₹{_group_inr(round(float(value)))}"


def _retailer_label(value):
    value = str(value or "").lower().removeprefix("www.")
    return RETAILER_LABELS.get(value, value or "Unknown retailer")


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _relative(value, now):
    timestamp = value if isinstance(value, datetime) else _parse_ts(value)
    if not timestamp:
        return "No data"
    seconds = max(0, int((now - timestamp).total_seconds()))
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    return f"{hours // 24}d ago"


def _freshness(record, now):
    value = record.get("last_success_ts")
    timestamp = _parse_ts(value)
    if not timestamp:
        return "No data"
    prefix = "Fresh" if now - timestamp <= timedelta(hours=24) else "Stale"
    return f"{prefix} · {_relative(timestamp, now)}"


def _is_current(value, now):
    """Return whether a timestamp/offer is still inside the 24-hour display window."""
    if isinstance(value, dict):
        value = value.get("last_success_ts")
    timestamp = _parse_ts(value)
    return bool(timestamp and now - timestamp <= timedelta(hours=24))


def _source_label(listing, record):
    return record.get("last_source") or next(iter(listing.get("source_urls", {})), "—")


def _product_state(state, product):
    return state.get("products", {}).get(product["id"], {})


def _status(state, product):
    return _product_state(state, product).get("status", "idle")


def _score(state, product):
    return _number((_product_state(state, product).get("last_verdict") or {}).get("score"))


def _offer_data(product, state):
    product_state = _product_state(state, product)
    recommended_id = product_state.get("recommended_listing_id")
    offers = []
    for listing in product.get("listings", []):
        listing_state = state.get("listings", {}).get(listing["id"], {})
        offers.append({
            "listing": listing,
            "state": listing_state,
            "verdict": listing_state.get("last_verdict") or {},
            "best": listing["id"] == recommended_id,
        })
    return offers


def _verdict_line(products, state, now):
    count = sum(1 for product in products if _status(state, product) == "buy")
    if count == 0:
        headline = "No products in the buy zone"
    elif count == 1:
        headline = "1 product in the buy zone"
    else:
        headline = f"{count} products in the buy zone"
    # Freshness must describe DATA, not effort. last_checked_ts is set before the
    # fetch is attempted and survives total failure; last_success_ts does not.
    listings_state = state.get("listings") or {}
    product_timestamps = []
    for product in products:
        timestamps = []
        for listing in product.get("listings", []):
            stamp = _parse_ts(listings_state.get(listing.get("id"), {}).get("last_success_ts"))
            if stamp:
                timestamps.append(stamp)
        product_timestamps.append(max(timestamps, default=None))

    priced = [stamp for stamp in product_timestamps if stamp]
    missing = sum(stamp is None for stamp in product_timestamps)
    stale = sum(bool(stamp and now - stamp > timedelta(hours=24)) for stamp in product_timestamps)
    if not priced:
        detail = "no successful check yet"
    elif stale or missing:
        problems = []
        if stale:
            problems.append(f"{stale} stale")
        if missing:
            problems.append(f"{missing} without data")
        detail = f"{' · '.join(problems)} · newest price {_relative(max(priced), now)}"
    else:
        detail = f"all current · oldest price {_relative(min(priced), now)}"
    return headline, f"{len(products)} tracked · {detail}"


STYLE = r"""
:root{--surface:#14171C;--surface2:#1B1F26;--line:#252A33;--txt:#E9ECF1;--dim:#8B93A1;
--dimmer:#5C6472;--go:#3FB950;--go-dim:#1E6E32;--warn:#D29922;--idle:#687386}
*{box-sizing:border-box;margin:0}
html{color-scheme:dark}
body{background:#0F1116;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
color:var(--txt);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;padding:26px;
max-width:940px;min-height:100vh;margin:0 auto}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
.verdict{display:flex;align-items:baseline;gap:10px;padding:0 0 18px;border-bottom:1px solid var(--line);
margin-bottom:18px;flex-wrap:wrap}.verdict h1{font-size:19px;font-weight:650;letter-spacing:-.01em}
.verdict .sub{color:var(--dim);font-size:12.5px}.cards{display:flex;flex-direction:column;gap:10px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;
transition:border-color .18s,box-shadow .18s,background .18s}.card:hover{border-color:#38404D}
.card.open{border-color:#343C48;box-shadow:0 16px 42px rgba(0,0,0,.18)}
.card.buy{border-color:var(--go-dim);background:linear-gradient(90deg,rgba(63,185,80,.05),transparent 42%)}
.card.watch{background:linear-gradient(90deg,rgba(210,153,34,.035),transparent 38%)}
.head{appearance:none;width:100%;display:grid;grid-template-columns:4px 1fr auto auto;gap:16px;align-items:center;
padding:15px 17px;cursor:pointer;user-select:none;background:transparent;border:0;color:inherit;text-align:left;font:inherit}
.head:focus-visible{outline:2px solid #8AB4F8;outline-offset:-3px}.head:hover .nm{color:#FFF}
.rail{width:4px;height:38px;border-radius:3px;background:var(--dimmer)}.card.buy .rail{background:var(--go)}
.card.watch .rail{background:var(--warn)}.card.idle .rail{background:var(--idle)}
.nm{font-size:13.5px;font-weight:550;letter-spacing:-.005em;transition:color .15s}.sub2{color:var(--dim);font-size:11.5px;margin-top:3px}
.pricewrap{text-align:right}.price{font-size:23px;font-weight:680;letter-spacing:-.02em}.card.buy .price{color:var(--go)}
.delta{font-size:11.5px;color:var(--dim);margin-top:2px}.meter{width:74px;text-align:center}
.bar{height:5px;background:#242932;border-radius:3px;overflow:hidden}.fill{height:100%;border-radius:3px;background:var(--dimmer)}
.card.buy .fill{background:var(--go)}.card.watch .fill{background:var(--warn)}
.mlabel{font-size:10px;color:var(--dimmer);margin-top:5px;letter-spacing:.055em;text-transform:uppercase}
.body{display:grid;grid-template-rows:0fr;transition:grid-template-rows .34s cubic-bezier(.2,.8,.2,1)}
.card.open .body{grid-template-rows:1fr}.body-clip{min-height:0;overflow:hidden}
.inner{padding:4px 17px 18px;border-top:1px solid var(--line);margin-top:2px}.ranges{display:flex;gap:5px;margin:15px 0 12px}
.r{background:transparent;border:1px solid var(--line);color:var(--dim);padding:4px 11px;border-radius:7px;font-size:11.5px;cursor:pointer;font-family:inherit}
.r:hover{border-color:#3A424F;color:var(--txt)}.r:focus-visible{outline:2px solid #8AB4F8;outline-offset:2px}
.r.on{background:var(--surface2);color:var(--txt);border-color:#3A424F}.chart-title{display:flex;justify-content:space-between;
font-size:11.5px;color:var(--dim);margin:3px 0 7px}.chart-range{color:var(--dimmer)}
.chart{height:164px;position:relative}.chart canvas{width:100%!important;height:164px!important}
.chart-message{height:164px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;
color:var(--dimmer);text-align:center;font-size:12px}.chart-message.loading:before{content:"";width:16px;height:16px;
border:2px solid #303744;border-top-color:#8B93A1;border-radius:50%;animation:spin .75s linear infinite}
.retry{background:transparent;border:1px solid #3A424F;color:var(--txt);padding:5px 10px;border-radius:7px;cursor:pointer;font:inherit;font-size:11.5px}
@keyframes spin{to{transform:rotate(360deg)}}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:15px}
.st{background:var(--surface2);padding:11px 13px}.stl{font-size:10px;color:var(--dimmer);text-transform:uppercase;letter-spacing:.055em}
.stv{font-size:15px;font-weight:600;margin-top:4px}.stv.go{color:var(--go)}.why{margin-top:14px;display:flex;flex-direction:column;gap:7px}
.rsn{display:flex;gap:9px;align-items:flex-start;font-size:12.5px;color:#C3CAD6}.dot{width:5px;height:5px;border-radius:50%;background:var(--go);margin-top:6px;flex:none}.dot.w{background:var(--warn)}
.offers{margin-top:16px;border:1px solid var(--line);border-radius:10px;overflow:hidden}.offer{display:grid;grid-template-columns:1.2fr .8fr .9fr .9fr auto;gap:8px;align-items:center;padding:9px 11px;background:var(--surface2);border-bottom:1px solid var(--line);font-size:11.5px}
.offer:last-child{border-bottom:0}.offer-h{color:var(--dimmer);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.best{color:var(--go);font-size:10px;text-transform:uppercase;margin-left:5px}
.open-link{color:#8AB4F8;text-decoration:none}.open-link:hover{text-decoration:underline}
.acts{display:flex;gap:9px;margin-top:16px}.btn{flex:1;text-align:center;padding:9px;border-radius:9px;font-size:12.5px;font-weight:560;
cursor:pointer;border:1px solid var(--line);background:var(--surface2);color:var(--txt);font-family:inherit;text-decoration:none}
.btn:hover{border-color:#3A424F;background:#20252E}.btn.p{background:var(--go);border-color:var(--go);color:#08210E}.btn.p:hover{background:#55C768}
.foot{margin-top:16px;color:var(--dimmer);font-size:11px;text-align:center}
@media(max-width:600px){body{padding:18px 12px}.head{grid-template-columns:4px 1fr auto;gap:11px}.meter{display:none}.stats{grid-template-columns:repeat(2,1fr)}
.offer{grid-template-columns:1.1fr .8fr .8fr auto}.offer .offer-source{display:none}.acts{flex-direction:column}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
"""


SCRIPT = r"""
(function(){
 const RANGE_DAYS={"1M":30,"3M":90,"6M":180,"1Y":365,"All":null};
 const chartCache=new Map(),dataCache=new Map();
 function rgba(hex,alpha){const raw=hex.replace("#","");return "rgba("+parseInt(raw.slice(0,2),16)+","+parseInt(raw.slice(2,4),16)+","+parseInt(raw.slice(4,6),16)+","+alpha+")"}
 function message(holder,text,kind,retry){holder.innerHTML='<div class="chart-message '+(kind||'')+'"><span>'+text+'</span>'+(retry?'<button type="button" class="retry">Retry chart</button>':'')+'</div>'}
 function readData(path){if(dataCache.has(path))return Promise.resolve(dataCache.get(path));return fetch(path).then(function(r){if(!r.ok)throw new Error("History request failed");return r.json()}).then(function(d){if(!Array.isArray(d))throw new Error("Invalid history data");dataCache.set(path,d);return d})}
 function nativeChart(holder,points,low,target,color){
  const canvas=document.createElement("canvas"),ctx=canvas.getContext("2d"),height=164;
  const stamps=points.map(function(p){return new Date(p.date+"T00:00:00").getTime()}),firstStamp=stamps[0],lastStamp=stamps[stamps.length-1];
  canvas.setAttribute("role","img");canvas.setAttribute("aria-label","Price history for "+(holder.dataset.retailer||"this product"));holder.innerHTML="";holder.appendChild(canvas);
  let width=0,active=-1;
  function draw(index){
   const rect=holder.getBoundingClientRect(),nextWidth=Math.max(280,Math.round(rect.width)),dpr=Math.min(window.devicePixelRatio||1,2);width=nextWidth;
   if(canvas.width!==width*dpr||canvas.height!==height*dpr){canvas.width=width*dpr;canvas.height=height*dpr;canvas.style.width=width+"px";canvas.style.height=height+"px"}
   ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);ctx.font="10px system-ui";ctx.lineWidth=1;
   const area={left:48,right:width-10,top:10,bottom:height-23},values=points.map(function(p){return Number(p.price)}),rawMin=Math.min.apply(null,values),rawMax=Math.max.apply(null,values),spread=Math.max(rawMax-rawMin,Math.max(rawMax*.08,1)),min=Math.max(0,rawMin-spread*.18),max=rawMax+spread*.18;
   const x=function(i){return firstStamp===lastStamp?(area.left+area.right)/2:area.left+(stamps[i]-firstStamp)*(area.right-area.left)/(lastStamp-firstStamp)},y=function(value){return area.bottom-(value-min)*(area.bottom-area.top)/(max-min)};
   ctx.textAlign="right";ctx.textBaseline="middle";for(let i=0;i<4;i++){const value=min+(max-min)*i/3,py=y(value);ctx.strokeStyle="rgba(38,43,53,.72)";ctx.beginPath();ctx.moveTo(area.left,py);ctx.lineTo(area.right,py);ctx.stroke();ctx.fillStyle="#6B7280";ctx.fillText("₹"+Math.round(value).toLocaleString("en-IN"),area.left-7,py)}
   const tickCount=Math.min(5,points.length);ctx.fillStyle="#6B7280";ctx.textBaseline="bottom";for(let i=0;i<tickCount;i++){const pointIndex=Math.round(i*(points.length-1)/Math.max(tickCount-1,1)),date=new Date(points[pointIndex].date+"T00:00:00"),px=x(pointIndex);ctx.textAlign=i===0?"left":i===tickCount-1?"right":"center";ctx.fillText(date.toLocaleDateString("en-IN",{day:"numeric",month:"short"}),px,height-3)}
   const linePath=new Path2D();linePath.moveTo(x(0),y(values[0]));for(let i=1;i<values.length;i++)linePath.lineTo(x(i),y(values[i]));
   const fillPath=new Path2D();fillPath.moveTo(x(0),area.bottom);fillPath.lineTo(x(0),y(values[0]));for(let i=1;i<values.length;i++)fillPath.lineTo(x(i),y(values[i]));fillPath.lineTo(x(values.length-1),area.bottom);fillPath.closePath();
   const gradient=ctx.createLinearGradient(0,area.top,0,area.bottom);gradient.addColorStop(0,rgba(color,.24));gradient.addColorStop(1,rgba(color,0));ctx.fillStyle=gradient;ctx.fill(fillPath);ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke(linePath);
   const references=[{value:low,label:"all-time low",color:"#3FB950"},{value:target,label:"your target",color:"#8B93A1"}].filter(function(line){return Number.isFinite(line.value)&&line.value>0&&line.value>=min&&line.value<=max});references.forEach(function(line,index){const py=y(line.value),label=line.label+" ₹"+Math.round(line.value).toLocaleString("en-IN"),labelWidth=ctx.measureText(label).width+10,overlaps=references.slice(0,index).some(function(other){return Math.abs(y(other.value)-py)<16}),labelX=overlaps?area.right-labelWidth-1:area.left+1;ctx.setLineDash([3,4]);ctx.globalAlpha=.58;ctx.strokeStyle=line.color;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(area.left,py);ctx.lineTo(area.right,py);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=.96;ctx.textAlign="left";ctx.textBaseline="alphabetic";ctx.fillStyle="#14171C";ctx.fillRect(labelX,py-14,labelWidth,15);ctx.fillStyle=line.color;ctx.fillText(label,labelX+5,py-4);ctx.globalAlpha=1});
   const last=values.length-1;ctx.fillStyle=color;ctx.strokeStyle="#14171C";ctx.lineWidth=2;ctx.beginPath();ctx.arc(x(last),y(values[last]),3.5,0,Math.PI*2);ctx.fill();ctx.stroke();
   if(index>=0){const px=x(index),py=y(values[index]),label="₹"+values[index].toLocaleString("en-IN"),date=new Date(points[index].date+"T00:00:00").toLocaleDateString("en-IN",{day:"numeric",month:"short",year:"numeric"});ctx.strokeStyle="rgba(139,147,161,.45)";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(px,area.top);ctx.lineTo(px,area.bottom);ctx.stroke();ctx.fillStyle=color;ctx.beginPath();ctx.arc(px,py,4,0,Math.PI*2);ctx.fill();const boxW=Math.max(ctx.measureText(label).width,ctx.measureText(date).width)+18,boxX=Math.min(Math.max(px-boxW/2,area.left),area.right-boxW),boxY=Math.max(area.top,py-49);ctx.fillStyle="#20252E";ctx.strokeStyle="#343C48";ctx.fillRect(boxX,boxY,boxW,38);ctx.strokeRect(boxX+.5,boxY+.5,boxW-1,37);ctx.textAlign="left";ctx.fillStyle="#8B93A1";ctx.fillText(date,boxX+9,boxY+14);ctx.fillStyle="#E9ECF1";ctx.fillText(label,boxX+9,boxY+29)}
  }
  function move(event){const rect=canvas.getBoundingClientRect(),relative=Math.max(0,Math.min(1,(event.clientX-rect.left-48)/Math.max(rect.width-58,1))),wanted=firstStamp+relative*(lastStamp-firstStamp);active=stamps.reduce(function(best,stamp,index){return Math.abs(stamp-wanted)<Math.abs(stamps[best]-wanted)?index:best},0);draw(active)}
  function leave(){active=-1;draw(-1)}
  canvas.addEventListener("mousemove",move);canvas.addEventListener("mouseleave",leave);const observer="ResizeObserver" in window?new ResizeObserver(function(){draw(active)}):null;if(observer)observer.observe(holder);draw(-1);
  return {destroy:function(){if(observer)observer.disconnect();canvas.removeEventListener("mousemove",move);canvas.removeEventListener("mouseleave",leave)}}
 }
 function render(row,range){const holder=row.querySelector(".chart"),path=holder.dataset.chartPath,low=Number(holder.dataset.low),target=holder.dataset.target?Number(holder.dataset.target):null,title=row.querySelector(".chart-range");
  if(title)title.textContent=range+" · daily lows";
  if(!path){message(holder,"No price history yet");return}
  message(holder,"Loading price history…","loading");
  readData(path).then(function(points){if(!points.length){message(holder,"No price history yet");return}
   const days=RANGE_DAYS[range],last=new Date(points[points.length-1].date),cut=days===null?null:new Date(last.getTime()-days*86400000),selected=days===null?points:points.filter(function(p){return new Date(p.date)>=cut});
   if(!selected.length){message(holder,"No price history in this range");return}
   const old=chartCache.get(row);if(old)old.destroy();chartCache.set(row,nativeChart(holder,selected,low,target,holder.dataset.color))
  }).catch(function(error){console.error("Price chart render failed",error);message(holder,"Price chart unavailable","",true)})}
 function setOpen(card,open){card.classList.toggle("open",open);const head=card.querySelector(".head"),body=card.querySelector(".body");head.setAttribute("aria-expanded",String(open));body.setAttribute("aria-hidden",String(!open))}
 function openCard(card){const was=card.classList.contains("open");document.querySelectorAll(".card.open").forEach(function(c){if(c!==card)setOpen(c,false)});setOpen(card,!was);if(was)return;const selected=card.querySelector(".r.on")||card.querySelector(".r[data-range='6M']");render(card,selected.dataset.range)}
 document.querySelectorAll(".head").forEach(function(h){h.addEventListener("click",function(){openCard(h.closest(".card"))})});
 document.querySelectorAll(".ranges").forEach(function(box){box.addEventListener("click",function(e){const button=e.target.closest(".r");if(!button)return;e.stopPropagation();box.querySelectorAll(".r").forEach(function(x){x.classList.remove("on");x.setAttribute("aria-pressed","false")});button.classList.add("on");button.setAttribute("aria-pressed","true");const card=box.closest(".card");if(card.classList.contains("open"))render(card,button.dataset.range)})});
 document.addEventListener("click",function(e){const retry=e.target.closest(".retry");if(!retry)return;const card=retry.closest(".card"),selected=card.querySelector(".r.on");render(card,selected.dataset.range)});
})();
"""


def _card(product, state, chart_paths, now):
    product_state = _product_state(state, product)
    status = _status(state, product)
    recommended_verdict = product_state.get("last_verdict") or {}
    # No BUYABLE offer does not mean no data: an out-of-stock listing is filtered
    # out of `fresh` upstream and lands in stale_offers with its verdict intact.
    # Recompute recency at render time because the stored `fresh` flag describes
    # the last tracker run, not the moment this page is generated.
    stale_offers = product_state.get("stale_offers") or []
    fallback = next(
        (
            offer for offer in stale_offers
            if _is_current(offer, now) and not offer.get("in_stock", True)
        ),
        {},
    )
    using_fallback = not recommended_verdict and bool(fallback)
    verdict = recommended_verdict or fallback
    out_of_stock = using_fallback
    recommended_id = product_state.get("recommended_listing_id")
    offer_items = _offer_data(product, state)
    recommended = next((item for item in offer_items if item["listing"]["id"] == recommended_id), None)
    fallback_id = fallback.get("listing_id") if using_fallback else None
    fallback_item = next(
        (item for item in offer_items if item["listing"]["id"] == fallback_id),
        None,
    )
    chart_offer = recommended or fallback_item or (offer_items[0] if offer_items else None)
    recommended_listing = recommended["listing"] if recommended else None
    chart_listing = chart_offer["listing"] if chart_offer else None
    display_state = chart_offer["state"] if chart_offer else {}
    display_listing = recommended_listing or chart_listing
    price = _number(verdict.get("price"))
    score = _number(verdict.get("score"))
    high = _number(verdict.get("life_high") or display_state.get("site_high"))
    low = _number(verdict.get("life_low") or display_state.get("site_low"))
    if verdict.get("basis"):
        median = _number(verdict.get("median") or verdict.get("life_avg") or display_state.get("site_avg"))
        median_label = "Lifetime average"
    elif verdict.get("median") is not None:
        median = _number(verdict.get("median"))
        median_label = "180-day median"
    else:
        median = _number(verdict.get("life_avg") or display_state.get("site_avg"))
        median_label = "Lifetime average" if median is not None else "180-day median"
    below_peak = ((high - price) / high * 100) if high and price is not None and high >= price else None
    retailer = _retailer_label(display_listing.get("retailer")) if display_listing else "Not tracked"
    chart_retailer = _retailer_label(chart_listing.get("retailer")) if chart_listing else retailer
    freshness = _freshness(display_state, now) if display_listing else "No data"
    stock_note = " · Out of stock" if out_of_stock else ""
    current_offers = []
    for item in offer_items:
        record = item["state"]
        offer_verdict = item["verdict"]
        offer_price = _number(offer_verdict.get("price") or record.get("last_price"))
        in_stock = offer_verdict.get("in_stock", record.get("last_in_stock", True))
        if offer_price is not None and in_stock and _is_current(record.get("last_success_ts"), now):
            current_offers.append((offer_price, item))
    comparison_note = ""
    if len(current_offers) > 1:
        current_offers.sort(key=lambda pair: (pair[0], pair[1]["listing"].get("retailer", "")))
        best_price, _ = current_offers[0]
        next_price, next_item = current_offers[1]
        next_retailer = _retailer_label(next_item["listing"].get("retailer"))
        saving = next_price - best_price
        if saving > 0:
            comparison_note = f" · Cheapest of {len(current_offers)} · {_money(saving)} less than {next_retailer}"
        else:
            comparison_note = f" · Cheapest of {len(current_offers)} · tied with {next_retailer}"
    elif len(offer_items) > 1:
        comparison_note = f" · {len(current_offers)} of {len(offer_items)} offers current"
    color = "#3FB950" if status == "buy" else "#D29922" if status == "watch" else "#4B85D6"
    listing_id = chart_listing["id"] if chart_listing else (product.get("listings") or [{"id": ""}])[0]["id"]
    chart_path = chart_paths.get(listing_id, "")
    target = product.get("target")
    reasons = verdict.get("reasons") or ["No fresh verdict yet."]
    score_text = f"{score:.0f}" if score is not None else "—"
    fill = max(0, min(100, score or 0))
    if out_of_stock:
        delta = "Out of stock"
    elif price is None:
        delta = "No fresh offer"
    elif low is not None and price <= low:
        delta = "at all-time low"
    elif high is not None and price > high:
        delta = "above all-time high"
    elif below_peak is not None:
        delta = f"{below_peak:.0f}% below peak"
    else:
        delta = "No range data"

    offer_rows = []
    for item in offer_items:
        listing = item["listing"]
        record = item["state"]
        offer_verdict = item["verdict"]
        offer_stock = offer_verdict.get("in_stock", record.get("last_in_stock", True))
        offer_freshness = _freshness(record, now)
        if offer_stock is False:
            offer_freshness += " · Out of stock"
        offer_rows.append(
            '<div class="offer">'
            f'<span>{_escape(_retailer_label(listing.get("retailer")))}{"<span class=best>Best</span>" if item["best"] else ""}</span>'
            f'<span class="num">{_escape(_money(_number(offer_verdict.get("price") or record.get("last_price"))))}</span>'
            f'<span>{_escape(offer_freshness)}</span>'
            f'<span class="offer-source">{_escape(_source_label(listing, record))}</span>'
            f'<a class="open-link" href="{_escape(listing.get("url"), quote=True)}" target="_blank" rel="noopener">Open</a>'
            '</div>'
        )
    if not offer_rows:
        offer_rows.append('<div class="offer"><span>No confirmed offers</span></div>')

    range_buttons = "".join(
        f'<button type="button" class="r{" on" if label == "6M" else ""}" data-range="{label}" '
        f'aria-pressed="{"true" if label == "6M" else "false"}">{label}</button>'
        for label in ("1M", "3M", "6M", "1Y", "All")
    )
    reasons_html = "".join(
        f'<div class="rsn"><span class="dot{" w" if not verdict.get("alert") else ""}"></span><span>{_escape(reason)}</span></div>'
        for reason in reasons
    )
    stats = (
        f'<div class="st"><div class="stl">All-time low</div><div class="stv num go">{_escape(_money(low))}</div></div>'
        f'<div class="st"><div class="stl">{_escape(median_label)}</div><div class="stv num">{_escape(_money(median))}</div></div>'
        f'<div class="st"><div class="stl">All-time high</div><div class="stv num">{_escape(_money(high))}</div></div>'
        f'<div class="st"><div class="stl">Your target</div><div class="stv num">{_escape(_money(target))}</div></div>'
    )
    chart_attrs = (
        f' data-chart-path="{_escape(chart_path, quote=True)}" data-color="{color}"'
        f' data-low="{_escape(low if low is not None else "", quote=True)}"'
        f' data-target="{_escape(target if target is not None else "", quote=True)}"'
        f' data-retailer="{_escape(chart_retailer, quote=True)}"'
    )
    details_id = f"details-{listing_id or product.get('id', 'product')}"
    actions = ""
    if display_listing:
        primary_url = display_listing.get("url")
        source_name = display_state.get("last_source")
        history_url = (
            display_state.get("last_source_url")
            or display_listing.get("source_urls", {}).get(source_name)
            or next(iter(display_listing.get("source_urls", {}).values()), None)
        )
        action_links = []
        if primary_url:
            action_links.append(
                f'<a class="btn p" href="{_escape(primary_url, quote=True)}" target="_blank" rel="noopener">'
                f'Open on {_escape(retailer)}</a>'
            )
        if history_url:
            action_links.append(
                f'<a class="btn" href="{_escape(history_url, quote=True)}" target="_blank" rel="noopener">'
                'View price history</a>'
            )
        if action_links:
            actions = f'<div class="acts">{"".join(action_links)}</div>'
    return (
        f'<div class="card {_escape(status, quote=True)}" data-listing="{_escape(listing_id, quote=True)}">'
        f'<button type="button" class="head" aria-expanded="false" aria-controls="{_escape(details_id, quote=True)}"><div class="rail"></div>'
        f'<div><div class="nm">{_escape(product.get("name"))}</div><div class="sub2">{_escape(retailer)} · {_escape(freshness)}{_escape(stock_note)}{_escape(comparison_note)}</div></div>'
        f'<div class="meter"><div class="bar"><div class="fill" style="width:{fill:.0f}%"></div></div><div class="mlabel num">{_escape(score_text)} / 100</div></div>'
        f'<div class="pricewrap"><div class="price num">{_escape(_money(price))}</div><div class="delta num">{_escape(delta)}</div></div></button>'
        f'<div class="body" id="{_escape(details_id, quote=True)}" aria-hidden="true"><div class="body-clip"><div class="inner">'
        f'<div class="ranges" aria-label="Chart range">{range_buttons}</div><div class="chart-title"><span>Price history — {_escape(chart_retailer)}</span><span class="chart-range">6M · daily lows</span></div>'
        f'<div class="chart" aria-live="polite"{chart_attrs}><div class="chart-message">Expand to load price history</div></div>'
        f'<div class="stats">{stats}</div><div class="why">{reasons_html}</div>'
        f'<div class="offers"><div class="offer offer-h"><span>Retailer</span><span>Price</span><span>Freshness</span><span class="offer-source">Source</span><span></span></div>{"".join(offer_rows)}</div>'
        f'{actions}</div></div></div></div>'
    )


def build(products, state, output_path=None, chart_dir=None, now=None):
    now = now or datetime.now(timezone.utc)
    output_path = output_path or OUT
    chart_dir = chart_dir or CHART_DATA_DIR
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    os.makedirs(chart_dir, exist_ok=True)

    chart_paths = {}
    for product in products:
        for listing in product.get("listings", []):
            listing_id = listing["id"]
            record = (state.get("listings") or {}).get(listing_id, {})
            points = provider_history(record) or daily_low(analyze.load_history(listing_id))
            chart_file = os.path.join(chart_dir, f"{listing_id}.json")
            with open(chart_file, "w", encoding="utf-8", newline="\n") as handle:
                json.dump([{"date": timestamp.date().isoformat(), "price": round(price, 2)} for timestamp, price in points], handle, separators=(",", ":"))
            chart_paths[listing_id] = os.path.relpath(chart_file, os.path.dirname(output_path)).replace(os.sep, "/")

    ordered = sorted(
        products,
        key=lambda product: (
            {"buy": 0, "watch": 1, "idle": 2}.get(_status(state, product), 2),
            -(_score(state, product) or -1),
            product.get("name", "").casefold(),
        ),
    )
    headline, sub = _verdict_line(products, state, now)
    cards = "".join(_card(product, state, chart_paths, now) for product in ordered)
    html_text = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"theme-color\" content=\"#0F1116\">"
        "<title>Price Sentinel</title><style>" + STYLE + "</style></head><body>"
        f'<div class="verdict"><h1>{_escape(headline)}</h1><span class="sub">{_escape(sub)}</span></div>'
        f'<div class="cards">{cards or "<p>No products tracked.</p>"}</div>'
        '<div class="foot">Tap any card to expand · charts load on demand</div>'
        f"<script>{SCRIPT}</script></body></html>"
    )
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(html_text)
    print(f"[dashboard] wrote {output_path}")


if __name__ == "__main__":
    with open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8") as handle:
        watchlist = json.load(handle)
    with open(os.path.join(ROOT, "data", "state.json"), encoding="utf-8") as handle:
        state = json.load(handle)
    build(watchlist.get("products", []), state)
