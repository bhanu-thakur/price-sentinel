"""Alert delivery: ntfy push (instant, phone) + SMTP email (durable record).

Both are free. Neither needs a bot token. Configure via env vars / GH secrets.
"""
import os
import smtplib
from email.message import EmailMessage

import requests

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
SMTP_HOST = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
MAIL_TO = (os.environ.get("MAIL_TO") or SMTP_USER).strip()


def _rupees(x):
    return f"Rs {x:,.0f}" if x is not None else "-"


def format_alert(v):
    lines = [f"{_rupees(v['price'])}  -  {v['name'][:70]}"]
    if v.get("median"):
        lines.append(
            f"90d: low {_rupees(v.get('min90'))} / median {_rupees(v['median'])} / high {_rupees(v.get('max90'))}"
        )
        lines.append(f"Deal score {v['score']}/100 (percentile {v.get('percentile', 0):.0f})")
    for r in v["reasons"]:
        lines.append(f"- {r}")
    return "\n".join(lines)


def push_ntfy(verdicts):
    if not NTFY_TOPIC or not verdicts:
        return False
    top = max(verdicts, key=lambda v: v["score"])
    title = f"Price drop: {top['name'][:45]}"
    body = "\n\n".join(format_alert(v) for v in verdicts)
    try:
        requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=body.encode("utf-8"),
            headers={
                "Title": title.encode("utf-8"),
                "Priority": "urgent" if top["score"] >= 75 else "high",
                "Tags": "moneybag",
                "Click": top["url"],
                "Actions": f"view, Open on Amazon, {top['url']}",
            },
            timeout=20,
        ).raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001 - never let alerting kill the run
        print(f"[ntfy] failed: {e}")
        return False


def send_email(verdicts):
    if not (SMTP_USER and SMTP_PASS and MAIL_TO) or not verdicts:
        return False
    top = max(verdicts, key=lambda v: v["score"])
    rows = "".join(
        f"""<tr>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{v['url']}" style="font-weight:600;color:#0b5">{v['name'][:80]}</a><br>
            <span style="font-size:22px;font-weight:700">{_rupees(v['price'])}</span>
            <span style="color:#888"> &nbsp;90d low {_rupees(v.get('min90'))} &middot; median {_rupees(v.get('median'))}</span><br>
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
        return
    ok_push = push_ntfy(verdicts)
    ok_mail = send_email(verdicts)
    print(f"[notify] {len(verdicts)} alert(s) | ntfy={ok_push} email={ok_mail}")
