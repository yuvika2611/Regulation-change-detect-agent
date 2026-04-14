"""
Free Alternatives - FINAL WORKING VERSION
Gemini 2.0 Flash + Gmail SMTP
All encoding issues fixed, rate limit handled with retry+delay
"""
import os, json, smtplib, time
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

def _debug_encoding(label: str, text: str):
    try:
        text.encode("ascii")
    except UnicodeEncodeError as e:
        print(f"  ❌ Non-ASCII detected in {label}: {repr(text[e.start:e.end])}")

def _clean(text):
    """Force text into standard UTF-8 and strip problematic whitespace."""
    if not text:
        return ""
    # Convert to string and handle non-breaking spaces immediately
    text = str(text).replace("\xa0", " ").replace("&nbsp;", " ")
    # Encode to utf-8, ignoring characters that can't be mapped, then decode back
    return text.encode("utf-8", "ignore").decode("utf-8").strip()
    

def analyze_with_gemini(publications: list) -> list:
    use_gemini = os.environ.get("USE_GEMINI", "false").lower() == "true"

    if not use_gemini:
        print("  ⚠️ Gemini disabled — using fallback analysis")
        return _smart_fallback(publications)
    
    # ✅ ADD HERE
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  ⚠️ No Gemini API key found")
        return _smart_fallback(publications)

    # keeping the Gemini code below (unchanged)

    try:
        import google.generativeai as genai
    except ImportError:
        os.system("pip install google-generativeai -q")
        import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    if not publications:
        return []

    pub_text = ""
    for i, pub in enumerate(publications, 1):
        pub_text += f"\n[{i}] SOURCE: {pub['source']}\n"
        pub_text += f"    TITLE: {pub.get('title','')}\n"
        pub_text += f"    TYPE: {pub.get('type','')}\n"
        if pub.get("abstract"):
            pub_text += f"    ABSTRACT: {pub['abstract']}\n"
        if pub.get("agency"):
            pub_text += f"    AGENCY: {pub['agency']}\n"

    prompt = f"""You are a senior compliance analyst for a US insurance and banking company.
Analyze these regulatory publications. Return a JSON array only.

For each publication return:
- "index": the [N] number
- "summary": 2-3 sentence plain English explanation
- "urgency": exactly "URGENT", "MONITOR", or "INFORMATIONAL"
- "teams": array from ["Claims","Compliance","Legal","Actuarial","Operations","Finance","IT","HR","Executive","Underwriting"]
- "checklist": array of 2-4 specific action items
- "deadline": deadline string or null
- "impact": one sentence on business impact
- "confidence": "high", "medium", or "low"

Return ONLY the JSON array. No markdown. No text before or after.

Publications:
{pub_text}"""

    # Try with retry on rate limit
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            analyses = json.loads(raw)

            for analysis in analyses:
                idx = analysis.get("index", 0) - 1
                if 0 <= idx < len(publications):
                    publications[idx]["summary"]    = analysis.get("summary", "")
                    publications[idx]["urgency"]    = analysis.get("urgency", "INFORMATIONAL")
                    publications[idx]["teams"]      = ", ".join(analysis.get("teams", ["Compliance"]))
                    publications[idx]["checklist"]  = analysis.get("checklist", [])
                    publications[idx]["deadline"]   = analysis.get("deadline")
                    publications[idx]["impact"]     = analysis.get("impact", "")
                    publications[idx]["confidence"] = analysis.get("confidence", "medium")

            print(f"  ✅ Gemini analyzed {len(publications)} publications")
            return publications

        except Exception as e:
            err = str(e)
            if "429" in err:
                wait = 35 * (attempt + 1)
                print(f"  ⏳ Rate limit hit — waiting {wait}s before retry {attempt+1}/3...")
                time.sleep(wait)
            else:
                print(f"  ⚠️  Gemini error: {e}")
                break

    print("  ⚠️  Gemini unavailable — using smart keyword analysis")
    print("  ⚠️  Using fallback (no AI)")
    return _smart_fallback(publications)


def generate_digest_summary_gemini(publications: list) -> str:
    """Generate executive summary with Gemini, fallback to auto-summary."""
    
    use_gemini = os.environ.get("USE_GEMINI", "false").lower() == "true"
    
    if not use_gemini:
        print("  ⚠️ Gemini disabled — using fallback summary")
        return _auto_summary(publications)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        return _auto_summary(publications)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        urgent  = [p for p in publications if p.get("urgency") == "URGENT"]
        monitor = [p for p in publications if p.get("urgency") == "MONITOR"]
        items   = "\n".join([
            f"- [{p.get('urgency','INFO')}] {p['source']}: {p['title']}"
            for p in publications[:15]
        ])

        prompt = f"""Write a 4-5 sentence executive summary of today's regulatory activity for a US compliance team.
{len(urgent)} urgent, {len(monitor)} to monitor out of {len(publications)} total.
Publications: {items}
Be direct. Name the most important items. Flowing prose, no bullet points."""

        try:
            response = model.generate_content(prompt)
            return response.text.strip()

        except Exception as e:
            if "429" in str(e):
                print("  ⚠️ Gemini rate limited — using fallback")
                return _auto_summary(publications)
            else:
                raise

    except Exception as e:
        print(f"  ⚠️ Summary error: {e}")

    return _auto_summary(publications)

def send_email_gmail(publications: list, executive_summary: str) -> bool:
    """Send digest via Gmail SMTP with explicit UTF-8 string conversion."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_user = os.environ.get("GMAIL_USER", "").strip().replace("\xa0", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip().replace("\xa0", "")
    to_email   = os.environ.get("TO_EMAIL", "") or gmail_user

    if not gmail_user or not gmail_pass:
        print("  ⚠️  Gmail configuration missing in .env")
        return False

    today = datetime.now().strftime("%B %d, %Y")
    
    # Clean the summary and subject line
    clean_summary = _clean(executive_summary)
    subject_text = _clean(f"Compliance Digest - {today} ({len(publications)} items)")

    # 1. Create the Container
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject_text
    msg["From"] = gmail_user
    msg["To"] = to_email

    # 2. Build the HTML (Ensure _build_html is using the cleaned summary)
    urgent = [p for p in publications if p.get("urgency") == "URGENT"]
    monitor = [p for p in publications if p.get("urgency") == "MONITOR"]
    info = [p for p in publications if p.get("urgency") == "INFORMATIONAL"]
    
    html_content = _build_html(publications, clean_summary, today, urgent, monitor, info)
    
    # 3. Attach as UTF-8
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        print("USER:", repr(gmail_user))
        print("PASS:", repr(gmail_pass))

        server.login(gmail_user, gmail_pass)
        
        # CRITICAL FIX: Convert the entire message object to a UTF-8 string
        server.sendmail(gmail_user, [to_email], msg.as_bytes())
        
        server.quit()
        print(f"  ✅ SUCCESS: Email sent to {to_email}")
        return True

    except Exception as e:
        print(f"  ❌ Gmail error: {str(e)}")
        return False


def _build_html(publications, executive_summary, today, urgent, monitor, info):
    def pub_block(p):
        colors = {"URGENT": "#ef4444", "MONITOR": "#f59e0b", "INFORMATIONAL": "#22c55e"}
        c = colors.get(p.get("urgency", "INFORMATIONAL"), "#22c55e")
        checklist_html = "".join(
            f"<li style='margin:4px 0'>{_clean(item)}</li>"
            for item in (p.get("checklist") or [])
        )
        checklist = f"<ul style='margin:8px 0 0 16px'>{checklist_html}</ul>" if checklist_html else ""
        deadline  = f"<p style='color:#dc2626;font-size:12px;margin:6px 0 0'>Deadline: {_clean(p['deadline'])}</p>" if p.get("deadline") else ""
        src_link  = f'<a href="{p.get("url","")}" style="font-size:12px;color:#2563eb">View source</a>' if p.get("url") else ""
        return f"""
        <div style="border-left:3px solid {c};padding:14px 16px;margin:10px 0;background:#f9fafb;border-radius:0 8px 8px 0">
          <div style="margin-bottom:6px">
            <span style="background:{c}20;color:{c};font-size:11px;padding:2px 8px;border-radius:4px;font-weight:700">{p.get("urgency","INFO")}</span>
            <span style="background:#6366f120;color:#4f46e5;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px">{_clean(p.get("source",""))}</span>
          </div>
          <p style="font-weight:600;font-size:14px;color:#111827;margin:0 0 6px">{_clean(p.get("title",""))}</p>
          <p style="font-size:13px;color:#4b5563;margin:0 0 6px;line-height:1.6">{_clean(p.get("summary","Manual review required."))}</p>
          {checklist}
          <p style="font-size:12px;color:#6b7280;margin:8px 0 4px">Action: <strong>{_clean(p.get("teams","Compliance"))}</strong></p>
          {deadline}
          {src_link}
        </div>"""

    urgent_html  = "".join(pub_block(p) for p in urgent)  or "<p style='color:#6b7280'>None today.</p>"
    monitor_html = "".join(pub_block(p) for p in monitor) or "<p style='color:#6b7280'>None today.</p>"
    info_html    = "".join(pub_block(p) for p in info)    or "<p style='color:#6b7280'>None today.</p>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#111827">
  <div style="background:#0f172a;color:white;padding:24px;border-radius:12px 12px 0 0">
    <h1 style="margin:0;font-size:20px">ComplianceAI - Daily Digest</h1>
    <p style="margin:6px 0 0;color:#94a3b8;font-size:13px">{today}</p>
    <div style="display:flex;gap:24px;margin-top:14px">
      <div><span style="color:#ef4444;font-size:22px;font-weight:700">{len(urgent)}</span><br><span style="color:#94a3b8;font-size:11px">URGENT</span></div>
      <div><span style="color:#f59e0b;font-size:22px;font-weight:700">{len(monitor)}</span><br><span style="color:#94a3b8;font-size:11px">MONITOR</span></div>
      <div><span style="color:#22c55e;font-size:22px;font-weight:700">{len(info)}</span><br><span style="color:#94a3b8;font-size:11px">INFO</span></div>
      <div><span style="color:white;font-size:22px;font-weight:700">{len(publications)}</span><br><span style="color:#94a3b8;font-size:11px">TOTAL</span></div>
    </div>
  </div>
  <div style="background:#f1f5f9;padding:14px 18px;border-left:4px solid #6366f1">
    <p style="margin:0;font-size:13px;line-height:1.7"><strong>Summary:</strong> {_clean(executive_summary)}</p>
  </div>
  <div style="padding:16px 0">
    <h2 style="font-size:15px;color:#ef4444;margin:16px 0 8px">URGENT - Action Required</h2>{urgent_html}
    <h2 style="font-size:15px;color:#f59e0b;margin:20px 0 8px">MONITOR - Watch Closely</h2>{monitor_html}
    <h2 style="font-size:15px;color:#22c55e;margin:20px 0 8px">INFORMATIONAL</h2>{info_html}
  </div>
  <p style="font-size:11px;color:#94a3b8;text-align:center;border-top:1px solid #e2e8f0;padding-top:12px">
    ComplianceAI - Powered by Gemini AI and Gmail
  </p>
</body></html>"""


def _print_console(publications, executive_summary):
    print("\n" + "="*60)
    print(f"DIGEST - {datetime.now().strftime('%B %d, %Y')}")
    print("="*60)
    print(f"\n{executive_summary}\n")
    for p in publications:
        urgency = p.get("urgency", "INFO")
        emoji = {"URGENT": "🔴", "MONITOR": "🟡", "INFORMATIONAL": "🟢"}.get(urgency, "🟢")
        print(f"{emoji} [{p.get('source')}] {p.get('title','')[:80]}")
        if p.get("summary"):
            print(f"   {p['summary'][:120]}")


def _auto_summary(publications):
    """Smart auto-summary without AI — keyword based urgency."""
    urgent  = [p for p in publications if p.get("urgency") == "URGENT"]
    monitor = [p for p in publications if p.get("urgency") == "MONITOR"]
    sources = list(set(p.get("source","") for p in publications))
    summary = (
        f"Today's compliance digest covers {len(publications)} new regulatory publications "
        f"from {', '.join(sources[:4])}. "
    )
    if urgent:
        titles = "; ".join(p['title'][:60] for p in urgent[:2])
        summary += f"There are {len(urgent)} urgent items requiring immediate action: {titles}. "
    if monitor:
        summary += f"{len(monitor)} items require ongoing monitoring. "
    summary += "Review all items and assign action owners before end of week."
    return _clean(summary)


def _smart_fallback(publications):
    """
    Keyword-based urgency classification when Gemini is unavailable.
    Much better than generic 'Manual review required'.
    """
    URGENT_KEYWORDS = [
        "final rule", "effective date", "compliance date", "required by",
        "mandatory", "enforcement", "penalty", "fine", "violation",
        "immediate", "action required", "deadline", "cease", "prohibition"
    ]
    MONITOR_KEYWORDS = [
        "proposed rule", "notice of proposed", "request for comment",
        "advance notice", "study", "review", "consultation", "draft",
        "guidance", "update", "amendment", "revision", "proposed"
    ]
    TEAM_KEYWORDS = {
        "Claims":       ["claims", "loss", "settlement", "payout", "adjuster"],
        "Compliance":   ["compliance", "regulation", "regulatory", "enforcement"],
        "Legal":        ["legal", "litigation", "enforcement action", "court", "penalty"],
        "Actuarial":    ["actuarial", "reserve", "capital", "solvency", "risk-based"],
        "IT":           ["cybersecurity", "data", "technology", "digital", "system"],
        "Finance":      ["capital", "financial", "reporting", "accounting", "tax"],
        "Underwriting": ["underwriting", "premium", "rate", "pricing", "risk"],
        "HR":           ["employee", "training", "workforce", "staff"],
    }

    for pub in publications:
        title_lower = (pub.get("title","") + " " + pub.get("abstract","")).lower()

        # Determine urgency
        if any(kw in title_lower for kw in URGENT_KEYWORDS):
            pub["urgency"] = "URGENT"
        elif any(kw in title_lower for kw in MONITOR_KEYWORDS):
            pub["urgency"] = "MONITOR"
        else:
            pub["urgency"] = "INFORMATIONAL"

        # Determine teams
        matched_teams = []
        for team, keywords in TEAM_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                matched_teams.append(team)
        pub["teams"] = ", ".join(matched_teams) if matched_teams else "Compliance"

        # Generate basic summary
        source = pub.get("source", "regulator")
        title  = pub.get("title", "")
        pub["summary"] = (
            f"New {pub.get('type','publication')} from {source}: {title[:120]}. "
            f"Review this publication to assess applicability to your operations."
        )

        # Basic checklist
        pub["checklist"] = [
            f"Review full publication from {source}",
            "Assess impact on current policies and procedures",
            "Assign action owner if applicable",
        ]
        if pub["urgency"] == "URGENT":
            pub["checklist"].append("Escalate to compliance leadership immediately")

        pub["confidence"] = "low"

    return publications
