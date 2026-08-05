"""Alert delivery: ntfy push (instant, phone) + SMTP email (durable record).

Both are free. Neither needs a bot token. Configure via env vars / GH secrets.
"""
import os
import smtplib
from email.message import EmailMessage

import requests

import catalog

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
SMTP_HOST = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
MAIL_TO = (os.environ.get("MAIL_TO") or SMTP_USER).strip()


def _rupees(x):
    return f"Rs {x:,.0f}" if x is not None else "-"


_DANGLING = {"with", "and", "for", "the", "a", "an", "in", "of", "by", "to", "&", "-", "|"}


def _clip(text, limit):
    """Trim on a word boundary, without leaving a dangling connector word."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    words = text[:limit].split(" ")[:-1]
    while words and words[-1].strip(",").lower() in _DANGLING:
        words.pop()
    return " ".join(words)


def _lifetime(v):
    """Price range from the provider's own history.

    The 90-day figures are deliberately left out: they come from samples this
    tracker has collected itself, which for a young listing are all the same
    price, so they read as "low = median = high" and say nothing.
    """
    low, avg, high = v.get("life_low"), v.get("life_avg"), v.get("life_high")
    if not low:
        return None
    parts = [f"low {_rupees(low)}"]
    if avg:
        parts.append(f"avg {_rupees(avg)}")
    if high:
        parts.append(f"high {_rupees(high)}")
    return "All-time " + " · ".join(parts)


def alert_title(v):
    return f"{_rupees(v['price'])} - {_clip(v.get('name'), 38)}"


def format_alert(v):
    lines = list(v.get("reasons") or [])
    lifetime = _lifetime(v)
    if lifetime:
        lines += ["", lifetime]
    lines.append(
        f"Score {round(v['score'])}/100 · {catalog.retailer_label(v.get('retailer'))}"
    )
    return "\n".join(lines)


def push_ntfy(verdicts):
    """One push per product, so each carries its own title, link and button."""
    if not NTFY_TOPIC or not verdicts:
        return False
    delivered = True
    for v in sorted(verdicts, key=lambda item: item["score"], reverse=True):
        retailer = catalog.retailer_label(v.get("retailer"))
        try:
            requests.post(
                f"{NTFY_SERVER}/{NTFY_TOPIC}",
                data=format_alert(v).encode("utf-8"),
                headers={
                    "Title": alert_title(v).encode("utf-8"),
                    "Priority": "urgent" if v["score"] >= 75 else "high",
                    "Tags": "moneybag",
                    "Click": v["url"],
                    "Actions": f"view, Open on {retailer}, {v['url']}",
                },
                timeout=20,
            ).raise_for_status()
        except Exception as e:  # noqa: BLE001 - never let alerting kill the run
            # Report a partial failure as undelivered: re-sending one product
            # next run is better than silently burning its 7-day cooldown.
            print(f"[ntfy] {_clip(v.get('name'), 40)} failed: {e}")
            delivered = False
    return delivered


def send_email(verdicts):
    if not (SMTP_USER and SMTP_PASS and MAIL_TO) or not verdicts:
        return False
    top = max(verdicts, key=lambda v: v["score"])
    rows = "".join(
        f"""<tr>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{v['url']}" style="font-weight:600;color:#0b5">{v['name'][:80]}</a><br>
            <span style="font-size:22px;font-weight:700">{_rupees(v['price'])}</span>
            <span style="color:#888"> &nbsp;{_lifetime(v) or ''}</span><br>
            <span style="color:#555">Score {v['score']}/100 &middot; {'; '.join(v['reasons'])}</span>
          </td></tr>"""
        for v in verdicts
    )
    msg = EmailMessage()
    msg["Subject"] = f"Price Sentinel: {top['name'][:50]} at {_rupees(top['price'])}"
    msg["From"] = SMTP_USER
    msg["To"] = MAIL_TO
    msg.set_content("\n\n".join(format_alert(v) for v in verdicts))
    msg.add_alternative(
        f"<html><body style='font-family:system-ui,sans-serif'>"
        f"<h2 style='margin:0 0 12px'>Buy-zone hits</h2>"
        f"<table style='border-collapse:collapse;width:100%;max-width:620px'>{rows}</table>"
        f"<p style='color:#888;font-size:12px'>Price Sentinel</p></body></html>",
        subtype="html",
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[email] failed: {e}")
        return False


def dispatch(verdicts):
    if not verdicts:
        return False
    ok_push = push_ntfy(verdicts)
    ok_mail = send_email(verdicts)
    print(f"[notify] {len(verdicts)} alert(s) | ntfy={ok_push} email={ok_mail}")
    return ok_push or ok_mail
