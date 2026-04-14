"""
Main Orchestrator — FINAL FIXED VERSION
Uses Gemini 2.0 Flash + Gmail (both free)
Loads .env explicitly — no VS Code env injection needed
"""
import os, sys, json
from datetime import datetime
from pathlib import Path

# Load .env explicitly
ROOT_DIR = Path(__file__).parent.parent.absolute()
ENV_FILE = ROOT_DIR / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    print(f"✅ Loaded .env")
else:
    print(f"⚠️  No .env found — run: python setup.py")

sys.path.insert(0, str(ROOT_DIR))

# Import Gemini + Gmail (free alternatives)
from agents.scraper import fetch_all
from agents.free_alternatives import (
    analyze_with_gemini            as analyze_publications,
    generate_digest_summary_gemini as generate_digest_summary,
    send_email_gmail               as send_email_digest,
)
from agents.notifier import send_slack_alert
from database.db import get_db, init_db, log_audit

# NOTE: Do NOT import from agents.analyzer here — that uses Claude API


def is_seen(pub_id):
    db = get_db()
    return db.execute(
        "SELECT 1 FROM seen_publications WHERE pub_id=?", (pub_id,)
    ).fetchone() is not None


def mark_seen(pub_id):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO seen_publications (pub_id) VALUES (?)", (pub_id,))
    db.commit()


def save_publication(pub):
    db = get_db()
    try:
        db.execute("""INSERT OR IGNORE INTO publications
            (pub_id,source,title,url,pub_type,abstract,agency,urgency,
             summary,teams,deadline,impact,is_new,review_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pub.get("id"), pub.get("source"), pub.get("title"), pub.get("url"),
             pub.get("type"), pub.get("abstract"), pub.get("agency"),
             pub.get("urgency","INFORMATIONAL"), pub.get("summary"), pub.get("teams"),
             pub.get("deadline"), pub.get("impact"), 1,
             "pending" if pub.get("confidence") in ("low","medium") else "auto-approved"))
        db.commit()
    except Exception as e:
        print(f"  DB save error: {e}")


def save_checklists(pub):
    db = get_db()
    for team in [t.strip() for t in (pub.get("teams") or "Compliance").split(",")]:
        for item in (pub.get("checklist") or []):
            try:
                db.execute(
                    "INSERT INTO checklists (pub_id,team,item,due_date) VALUES (?,?,?,?)",
                    (pub.get("id"), team, item, pub.get("deadline"))
                )
            except:
                pass
    db.commit()


def save_digest(summary, pub_count, email_sent, slack_sent):
    db = get_db()
    db.execute("""INSERT INTO digests
        (pub_count,summary,urgent_count,monitor_count,info_count,email_sent,slack_sent)
        VALUES (?,?,?,?,?,?,?)""",
        (pub_count, summary,
         summary.count("URGENT"), summary.count("MONITOR"), summary.count("INFORMATIONAL"),
         1 if email_sent else 0, 1 if slack_sent else 0))
    db.commit()


def validate_config():
    print("\n🔧 Configuration check:")
    gemini = os.environ.get("GEMINI_API_KEY", "")
    gmail  = os.environ.get("GMAIL_USER", "")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    to     = os.environ.get("TO_EMAIL", "")
    print(f"   Gemini API:   {'✅ set' if gemini and gemini != 'your_key_here' else '❌ MISSING'}")
    print(f"   Gmail user:   {'✅ ' + gmail if gmail else '❌ MISSING'}")
    print(f"   App password: {'✅ set' if app_pw else '⚠️  missing'}")
    print(f"   Recipient:    {to or gmail or '❌ MISSING'}")
    if not gemini or gemini == "your_key_here":
        print("\n   ❌ GEMINI_API_KEY missing. Get free key at: aistudio.google.com")
        print("   Then run: python setup.py\n")
        return False
    return True


def run_daily_check(skip_email=False):
    print(f"\n{'='*65}")
    print(f"⚖️  ComplianceAI — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")

    init_db()
    if not validate_config():
        return {"error": "config incomplete"}

    log_audit("CHECK_STARTED", actor="scheduler")

    # Step 1: Fetch
    all_pubs = fetch_all()
    new_pubs = [
        p for p in all_pubs
        if not is_seen(p["id"]) and p.get("title") and len(p["title"]) > 10
    ]
    print(f"\n🆕 New publications: {len(new_pubs)}")

    if not new_pubs:
        print("✅ Nothing new today.")
        print("   Tip: run 'python setup.py' to reset\n")
        return {"new": 0}

    # Step 2: Analyze with Gemini 2.0 Flash
    print("\n🤖 Analyzing with Gemini 2.0 Flash (free)...")
    analyzed = []
    total_batches = -(-len(new_pubs) // 8)
    for i in range(0, len(new_pubs), 8):
        batch = new_pubs[i:i+8]
        print(f"  Batch {i//8+1}/{total_batches}: {len(batch)} items...")
        analyzed += analyze_publications(batch)

    # Step 3: Save to database
    print(f"\n💾 Saving {len(analyzed)} to database...")
    for pub in analyzed:
        save_publication(pub)
        save_checklists(pub)
        mark_seen(pub["id"])

    # Step 4: Executive summary
    print("\n📝 Generating executive summary...")
    exec_summary = generate_digest_summary(analyzed)
    print(f"   Done: {exec_summary[:80]}...")

    # Step 5: Send notifications
    email_sent = slack_sent = False
    if not skip_email:
        print("\n📧 Sending email...")
        email_sent = send_email_digest(analyzed, exec_summary)
        print("\n💬 Slack (urgent only)...")
        slack_sent = send_slack_alert(analyzed)

    # Step 6: Save digest record
    save_digest(exec_summary, len(analyzed), email_sent, slack_sent)
    log_audit("CHECK_COMPLETE", actor="scheduler",
              details=f"{len(analyzed)} processed, email={'sent' if email_sent else 'not sent'}")

    urgent  = len([p for p in analyzed if p.get("urgency") == "URGENT"])
    monitor = len([p for p in analyzed if p.get("urgency") == "MONITOR"])
    info    = len([p for p in analyzed if p.get("urgency") == "INFORMATIONAL"])

    print(f"\n{'='*65}")
    print(f"✅ COMPLETE")
    print(f"   🔴 Urgent:        {urgent}")
    print(f"   🟡 Monitor:       {monitor}")
    print(f"   🟢 Informational: {info}")
    print(f"   📧 Email:         {'✅ sent' if email_sent else '⚠️  check config'}")
    print(f"   💬 Slack:         {'✅ sent' if slack_sent else 'not configured (optional)'}")
    print(f"{'='*65}\n")

    return {"new": len(analyzed), "urgent": urgent}


if __name__ == "__main__":
    run_daily_check()
