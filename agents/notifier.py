"""
Notifier
=========
Handles all outbound notifications:
- Email digest via SendGrid (HTML, professional)
- Slack alerts (urgent items only, immediate)
- Logs every notification to audit trail
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Email ─────────────────────────────────────

def send_email_digest(publications: list[dict], executive_summary: str) -> bool:
    """Send full HTML email digest via SendGrid."""
    sg_key     = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL")
    to_email   = os.getenv("TO_EMAIL")

    if not all([sg_key, from_email, to_email]):
        print("  ⚠️  Email config missing — printing to console")
        _print_digest(publications, executive_summary)
        return False

    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        today = datetime.now().strftime("%B %d, %Y")
        urgent  = [p for p in publications if p.get("urgency") == "URGENT"]
        monitor = [p for p in publications if p.get("urgency") == "MONITOR"]
        info    = [p for p in publications if p.get("urgency") == "INFORMATIONAL"]

        subject = f"📋 Compliance Digest — {today} ({len(publications)} new"
        if urgent: subject += f", {len(urgent)} URGENT"
        subject += ")"

        html = _build_email_html(publications, executive_summary, today, urgent, monitor, info)

        msg = Mail(from_email=from_email, to_emails=to_email,
                   subject=subject, html_content=html)
        sg = sendgrid.SendGridAPIClient(api_key=sg_key)
        resp = sg.client.mail.send.post(request_body=msg.get())
        print(f"  ✅ Email sent (HTTP {resp.status_code})")
        return True
    except Exception as e:
        print(f"  ❌ Email failed: {e}")
        return False


def _build_email_html(publications, executive_summary, today, urgent, monitor, info) -> str:
    def pub_block(p):
        urgency_colors = {"URGENT":"#ef4444","MONITOR":"#f59e0b","INFORMATIONAL":"#22c55e"}
        color = urgency_colors.get(p.get("urgency","INFORMATIONAL"), "#22c55e")
        checklist_html = ""
        for item in (p.get("checklist") or []):
            checklist_html += f"<li style='margin:4px 0;color:#374151'>{item}</li>"
        checklist_section = f"<ul style='margin:8px 0 0 16px;padding:0'>{checklist_html}</ul>" if checklist_html else ""
        deadline = f"<p style='color:#dc2626;font-size:12px;margin:6px 0 0'>⏰ Deadline: {p['deadline']}</p>" if p.get("deadline") else ""
        confidence = p.get("confidence","medium")
        conf_color = {"high":"#16a34a","medium":"#d97706","low":"#dc2626"}.get(confidence,"#d97706")
        return f"""
        <div style="border-left:3px solid {color};padding:14px 16px;margin:10px 0;background:#f9fafb;border-radius:0 8px 8px 0">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
            <span style="background:{color}20;color:{color};font-size:11px;padding:2px 8px;border-radius:4px;font-weight:700">{p.get('urgency','INFO')}</span>
            <span style="background:#6366f120;color:#6366f1;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600">{p.get('source','')}</span>
            <span style="background:{conf_color}15;color:{conf_color};font-size:10px;padding:2px 6px;border-radius:4px">AI confidence: {confidence}</span>
          </div>
          <p style="font-weight:600;font-size:14px;color:#111827;margin:0 0 6px">{p.get('title','')}</p>
          <p style="font-size:13px;color:#4b5563;margin:0 0 6px;line-height:1.6">{p.get('summary','')}</p>
          {checklist_section}
          <p style="font-size:12px;color:#6b7280;margin:8px 0 0">👥 Action: <strong>{p.get('teams','Compliance')}</strong></p>
          {deadline}
          {'<a href="'+p['url']+'" style="font-size:12px;color:#2563eb">View source →</a>' if p.get('url') else ''}
        </div>"""

    urgent_blocks  = "".join(pub_block(p) for p in urgent)  or "<p style='color:#6b7280;font-size:13px'>None today.</p>"
    monitor_blocks = "".join(pub_block(p) for p in monitor) or "<p style='color:#6b7280;font-size:13px'>None today.</p>"
    info_blocks    = "".join(pub_block(p) for p in info)    or "<p style='color:#6b7280;font-size:13px'>None today.</p>"

    return f"""
    <html><head><meta charset='UTF-8'></head>
    <body style='font-family:-apple-system,Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#111827'>
      <div style='background:#0f172a;color:white;padding:24px;border-radius:12px 12px 0 0'>
        <h1 style='margin:0;font-size:20px'>⚖️ ComplianceAI — Daily Digest</h1>
        <p style='margin:6px 0 0;color:#94a3b8;font-size:13px'>{today}</p>
        <div style='display:flex;gap:20px;margin-top:16px'>
          <div><span style='color:#ef4444;font-size:22px;font-weight:700'>{len(urgent)}</span><br><span style='color:#94a3b8;font-size:11px'>URGENT</span></div>
          <div><span style='color:#f59e0b;font-size:22px;font-weight:700'>{len(monitor)}</span><br><span style='color:#94a3b8;font-size:11px'>MONITOR</span></div>
          <div><span style='color:#22c55e;font-size:22px;font-weight:700'>{len(info)}</span><br><span style='color:#94a3b8;font-size:11px'>INFO</span></div>
          <div><span style='color:white;font-size:22px;font-weight:700'>{len(publications)}</span><br><span style='color:#94a3b8;font-size:11px'>TOTAL</span></div>
        </div>
      </div>
      <div style='background:#f1f5f9;padding:16px 20px;border-left:4px solid #6366f1'>
        <p style='margin:0;font-size:13px;line-height:1.7;color:#374151'><strong>Executive Summary:</strong> {executive_summary}</p>
      </div>
      <div style='padding:20px 0'>
        <h2 style='font-size:15px;color:#ef4444;margin:0 0 8px'>🔴 URGENT — Action Required</h2>
        {urgent_blocks}
        <h2 style='font-size:15px;color:#f59e0b;margin:20px 0 8px'>🟡 MONITOR — Watch Closely</h2>
        {monitor_blocks}
        <h2 style='font-size:15px;color:#22c55e;margin:20px 0 8px'>🟢 INFORMATIONAL</h2>
        {info_blocks}
      </div>
      <div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px;margin-top:16px'>
        <p style='margin:0;font-size:11px;color:#94a3b8;text-align:center'>
          ComplianceAI · Powered by Claude AI · Sources: OCC, FinCEN, NAIC, Federal Register, SEC, CA DOI, NYDFS<br>
          ⚠️ Always verify with primary sources and legal counsel before taking compliance action.<br>
          AI confidence levels indicate certainty of analysis — LOW confidence items require mandatory human review.
        </p>
      </div>
    </body></html>"""


def _print_digest(publications, executive_summary):
    print("\n" + "="*70)
    print("COMPLIANCE DIGEST (email not configured)")
    print("="*70)
    print(f"\nEXECUTIVE SUMMARY:\n{executive_summary}\n")
    for p in publications:
        print(f"[{p.get('urgency','INFO')}] {p.get('source')}: {p.get('title')}")
        if p.get("summary"): print(f"  {p['summary']}")
        if p.get("checklist"):
            for item in p["checklist"]: print(f"  ✓ {item}")
        print()


# ── Slack ─────────────────────────────────────

def send_slack_alert(publications: list[dict], webhook_url: str = None) -> bool:
    """
    Sends urgent items to Slack immediately.
    webhook_url — override per-client. Falls back to SLACK_WEBHOOK_URL env var.
    """
    webhook = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        print("  ⚠️  No Slack webhook configured")
        return False

    urgent = [p for p in publications if p.get("urgency") == "URGENT"]
    if not urgent:
        print("  ℹ️  No urgent items — Slack alert skipped")
        return True

    blocks = [
        {"type":"header","text":{"type":"plain_text","text":f"🔴 {len(urgent)} URGENT Compliance Alert(s)"}},
        {"type":"section","text":{"type":"mrkdwn","text":f"*{datetime.now().strftime('%B %d, %Y')}* — ComplianceAI detected urgent regulatory updates requiring immediate action."}},
        {"type":"divider"},
    ]

    for p in urgent[:5]:  # Slack has block limits
        checklist_text = ""
        for item in (p.get("checklist") or [])[:3]:
            checklist_text += f"• {item}\n"

        blocks.append({
            "type":"section",
            "text":{"type":"mrkdwn",
                    "text":f"*[{p.get('source')}]* {p.get('title')}\n\n{p.get('summary','')}\n\n*Action required by:* {p.get('teams','Compliance')}"
                           + (f"\n*Deadline:* {p['deadline']}" if p.get("deadline") else "")
                           + (f"\n\n{checklist_text}" if checklist_text else "")},
        })
        if p.get("url"):
            blocks.append({"type":"actions","elements":[{
                "type":"button","text":{"type":"plain_text","text":"View Source"},
                "url":p["url"],"action_id":"view_source"
            }]})
        blocks.append({"type":"divider"})

    try:
        resp = requests.post(webhook, json={"blocks":blocks}, timeout=10)
        if resp.status_code == 200:
            print(f"  ✅ Slack alert sent ({len(urgent)} urgent items)")
            return True
        else:
            print(f"  ❌ Slack failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"  ❌ Slack error: {e}")
        return False


# ── Per-client notifications ─────────────────

def notify_all_clients(publications: list[dict], executive_summary: str):
    """Send notifications to all active clients based on their config."""
    from database.db import get_db, log_audit
    db = get_db()
    clients = db.execute(
        "SELECT * FROM clients WHERE status='active'"
    ).fetchall()

    for client in clients:
        client = dict(client)
        print(f"\n  📤 Notifying: {client['company_name']}")

        # Filter publications relevant to this client's industry
        industry = client.get("industry","both")
        relevant_pubs = _filter_by_industry(publications, industry)

        if not relevant_pubs:
            print(f"     No relevant publications for {industry}")
            continue

        # Email
        client_to = client.get("contact_email") or os.getenv("TO_EMAIL")
        if client_to:
            orig_to = os.environ.get("TO_EMAIL","")
            os.environ["TO_EMAIL"] = client_to
            email_sent = send_email_digest(relevant_pubs, executive_summary)
            os.environ["TO_EMAIL"] = orig_to

            db.execute(
                "INSERT INTO notifications (client_id, channel, status, sent_at) VALUES (?,?,?,?)",
                (client["id"], "email", "sent" if email_sent else "failed", datetime.now().isoformat())
            )
            log_audit("EMAIL_SENT", actor="system",
                      client_id=client["id"],
                      details=f"{len(relevant_pubs)} publications, email={'sent' if email_sent else 'failed'}")

        # Slack (if configured for this client)
        if client.get("slack_webhook"):
            slack_sent = send_slack_alert(relevant_pubs, client["slack_webhook"])
            db.execute(
                "INSERT INTO notifications (client_id, channel, status, sent_at) VALUES (?,?,?,?)",
                (client["id"], "slack", "sent" if slack_sent else "failed", datetime.now().isoformat())
            )

        db.commit()


def _filter_by_industry(publications: list[dict], industry: str) -> list[dict]:
    """Filter publications based on client industry."""
    if industry == "both":
        return publications
    banking_sources  = {"OCC","Federal Register","FinCEN","SEC","FDIC"}
    insurance_sources = {"NAIC","CA DOI","NYDFS"}
    if industry == "banking":
        return [p for p in publications
                if p.get("source") in banking_sources
                or p.get("source") == "Federal Register"]
    if industry == "insurance":
        return [p for p in publications
                if p.get("source") in insurance_sources
                or p.get("source") == "Federal Register"]
    return publications
