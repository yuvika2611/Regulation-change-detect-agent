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
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  ⚠️ No Gemini API key found")
        return _smart_fallback(publications)

    try:
        from google import genai
    except ImportError:
        os.system("pip install google-genai -q")
        from google import genai

    client = genai.Client(api_key=api_key)

    if not publications:
        return []

    pub_text = ""
    for i, pub in enumerate(publications, 1):
        pub_text += f"\n[{i}] SOURCE: {pub['source']}\n"
        pub_text += f"    TITLE: {pub.get('title','')}\n"
        pub_text += f"    TYPE: {pub.get('type','')}\n"
        if pub.get("abstract"):
            pub_text += f"    ABSTRACT: {pub['abstract'][:300]}\n"
        if pub.get("agency"):
            pub_text += f"    AGENCY: {pub['agency']}\n"

    prompt = f"""You are a senior compliance analyst for a US insurance and banking company.
Analyze these regulatory publications. Return a JSON array only.

For each publication return:
- "index": the [N] number
- "summary": 2-3 sentence plain English explanation of what SPECIFICALLY changed or was announced. Do NOT just repeat the title.
- "urgency": exactly "URGENT", "MONITOR", or "INFORMATIONAL"
- "teams": array from ["Claims","Compliance","Legal","Actuarial","Operations","Finance","IT","HR","Executive","Underwriting"]
- "checklist": array of 2-4 SPECIFIC action items (not generic advice)
- "deadline": deadline string or null
- "impact": one sentence on business impact
- "confidence": "high", "medium", or "low"

IMPORTANT: Do NOT write generic summaries. Each summary must explain what specifically changed.

Return ONLY the JSON array. No markdown. No text before or after.

Publications:
{pub_text}"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
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
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s
                print(f"  ⏳ Rate limit — waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
            else:
                print(f"  ⚠️  Gemini error: {e}")
                break

    print("  ⚠️  Gemini unavailable — using fallback")
    return _smart_fallback(publications)


def generate_digest_summary_gemini(publications: list) -> str:
    use_gemini = os.environ.get("USE_GEMINI", "false").lower() == "true"
    
    if not use_gemini:
        return _auto_summary(publications)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        return _auto_summary(publications)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        urgent  = [p for p in publications if p.get("urgency") == "URGENT"]
        monitor = [p for p in publications if p.get("urgency") == "MONITOR"]
        items   = "\n".join([
            f"- [{p.get('urgency','INFO')}] {p['source']}: {p['title']}"
            for p in publications[:15]
        ])

        prompt = f"""Write a 4-5 sentence executive summary of today's regulatory activity 
for a US compliance team. {len(urgent)} urgent, {len(monitor)} to monitor out of 
{len(publications)} total.
Publications: {items}
Be direct. Name the most important items. Flowing prose, no bullet points."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text.strip()

    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("  ⚠️ Gemini rate limited — using fallback summary")
        else:
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
        colors = {"URGENT": "#dc2626", "MONITOR": "#d97706", "INFORMATIONAL": "#059669"}
        bg_colors = {"URGENT": "#fef2f2", "MONITOR": "#fffbeb", "INFORMATIONAL": "#ecfdf5"}
        
        c = colors.get(p.get("urgency", "INFORMATIONAL"), "#059669")
        bg = bg_colors.get(p.get("urgency", "INFORMATIONAL"), "#ecfdf5")
        
        checklist_html = "".join(
            f"<li style='margin-bottom: 8px; color: #374151; font-size: 14px;'>✓ {_clean(item)}</li>"
            for item in (p.get("checklist") or [])
        )
        checklist = f"<ul style='list-style-type: none; padding: 0; margin: 15px 0; border-top: 1px solid #e5e7eb; padding-top: 15px;'>{checklist_html}</ul>" if checklist_html else ""
        
        deadline = f"<div style='margin-top: 15px; padding: 10px; background-color: #fee2e2; color: #991b1b; border-radius: 6px; font-weight: bold; font-size: 13px;'>⏰ Deadline: {_clean(p['deadline'])}</div>" if p.get("deadline") else ""
        
        src_link = f'<a href="{p.get("url","")}" style="display: inline-block; margin-top: 15px; text-decoration: none; color: #4f46e5; font-weight: bold; font-size: 14px;">Read Full Publication →</a>' if p.get("url") else ""
        
        return f"""
        <div style="background-color: #ffffff; border: 1px solid #e5e7eb; border-left: 4px solid {c}; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
          <div style="margin-bottom: 12px;">
            <span style="background-color: {bg}; color: {c}; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 20px; text-transform: uppercase;">{p.get("urgency","INFO")}</span>
            <span style="color: #6b7280; font-size: 13px; margin-left: 10px; font-weight: 500;">{_clean(p.get("source",""))}</span>
          </div>
          <h3 style="margin: 0 0 10px 0; color: #111827; font-size: 18px; line-height: 1.4;">{_clean(p.get("title",""))}</h3>
          <p style="margin: 0; color: #4b5563; font-size: 15px; line-height: 1.6;">{_clean(p.get("summary","Manual review required."))}</p>
          {checklist}
          <div style="margin-top: 15px; font-size: 13px; color: #6b7280;">
            <span style="background-color: #f3f4f6; padding: 4px 8px; border-radius: 4px;">👥 <strong>Action Required By:</strong> {_clean(p.get("teams","Compliance"))}</span>
          </div>
          {deadline}
          {src_link}
        </div>"""

    urgent_html  = "".join(pub_block(p) for p in urgent)  or "<p style='color:#6b7280; font-style: italic;'>No urgent items today.</p>"
    monitor_html = "".join(pub_block(p) for p in monitor) or "<p style='color:#6b7280; font-style: italic;'>No items to monitor today.</p>"
    info_html    = "".join(pub_block(p) for p in info)    or "<p style='color:#6b7280; font-style: italic;'>No informational items today.</p>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 20px; color: #111827;">
  <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
    
    <!-- HEADER -->
    <div style="background-color: #0f172a; padding: 30px 20px; text-align: center;">
      <h1 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: -0.5px;">⚖️ ComplianceAI Daily Digest</h1>
      <p style="color: #94a3b8; margin: 8px 0 0 0; font-size: 14px;">{today}</p>
    </div>

    <!-- STATS ROW -->
    <div style="display: flex; border-bottom: 1px solid #e5e7eb; background-color: #f8fafc;">
      <div style="flex: 1; text-align: center; padding: 15px; border-right: 1px solid #e5e7eb;">
        <div style="font-size: 24px; font-weight: bold; color: #dc2626;">{len(urgent)}</div>
        <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: bold; margin-top: 4px;">Urgent</div>
      </div>
      <div style="flex: 1; text-align: center; padding: 15px; border-right: 1px solid #e5e7eb;">
        <div style="font-size: 24px; font-weight: bold; color: #d97706;">{len(monitor)}</div>
        <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: bold; margin-top: 4px;">Monitor</div>
      </div>
      <div style="flex: 1; text-align: center; padding: 15px;">
        <div style="font-size: 24px; font-weight: bold; color: #059669;">{len(info)}</div>
        <div style="font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: bold; margin-top: 4px;">Info</div>
      </div>
    </div>

    <!-- EXECUTIVE SUMMARY -->
    <div style="padding: 25px 20px; background-color: #eef2ff; border-bottom: 1px solid #e5e7eb;">
      <h2 style="margin: 0 0 10px 0; font-size: 16px; color: #4338ca;">Executive Summary</h2>
      <p style="margin: 0; font-size: 15px; line-height: 1.6; color: #374151;">{_clean(executive_summary)}</p>
    </div>

    <!-- CONTENT -->
    <div style="padding: 30px 20px;">
      <h2 style="font-size: 18px; color: #dc2626; margin: 0 0 15px 0; border-bottom: 2px solid #fecaca; padding-bottom: 8px;">🔴 URGENT: Action Required</h2>
      {urgent_html}
      
      <h2 style="font-size: 18px; color: #d97706; margin: 40px 0 15px 0; border-bottom: 2px solid #fde68a; padding-bottom: 8px;">🟡 MONITOR: Watch Closely</h2>
      {monitor_html}
      
      <h2 style="font-size: 18px; color: #059669; margin: 40px 0 15px 0; border-bottom: 2px solid #a7f3d0; padding-bottom: 8px;">🟢 INFORMATIONAL</h2>
      {info_html}
    </div>

    <!-- FOOTER -->
    <div style="background-color: #f1f5f9; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb;">
      <p style="margin: 0; font-size: 12px; color: #64748b;">Powered by ComplianceAI • Generated by Gemini 2.0</p>
      <p style="margin: 5px 0 0 0; font-size: 11px; color: #94a3b8;">This is an AI-generated summary. Always consult legal counsel before taking compliance action.</p>
    </div>

  </div>
</body>
</html>"""


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
