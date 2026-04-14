"""
Claude Analyzer
================
Sends publications to Claude and gets back:
- Plain English summary
- Urgency level (URGENT / MONITOR / INFORMATIONAL)
- Team-specific action checklists
- Deadline detection
- Business impact statement
Returns structured JSON — safe to store and display.
"""
import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a senior compliance analyst at a US insurance and banking company.
You have 20 years of experience with OCC, NAIC, FinCEN, Federal Reserve, SEC, and state insurance regulations.
You are direct, precise, and always focused on practical action.
You never speculate — if something is unclear from the text, you say so.
You understand that wrong compliance advice can result in regulatory fines and legal liability."""

def analyze_publications(publications: list[dict]) -> list[dict]:
    """
    Sends up to 10 publications at once to Claude.
    Returns publications with analysis fields added.
    """
    if not publications:
        return []

    # Build input text
    pub_text = ""
    for i, pub in enumerate(publications, 1):
        pub_text += f"\n[{i}] SOURCE: {pub['source']}\n"
        pub_text += f"    TITLE: {pub['title']}\n"
        pub_text += f"    TYPE: {pub.get('type','')}\n"
        if pub.get("abstract"):
            pub_text += f"    ABSTRACT: {pub['abstract']}\n"
        if pub.get("agency"):
            pub_text += f"    AGENCY: {pub['agency']}\n"

    prompt = f"""Analyze these new US regulatory publications for an insurance and banking compliance team.

For EACH publication, return a JSON object with these exact fields:
- "index": integer (matching the [N] in input)
- "summary": 2-3 sentence plain English explanation. What changed, what was proposed, or what is required.
- "urgency": exactly one of "URGENT", "MONITOR", or "INFORMATIONAL"
  URGENT = requires action or response within 60 days
  MONITOR = developing situation, no immediate action but watch closely
  INFORMATIONAL = awareness only, no action required
- "teams": array of strings. Which teams must act? Choose from:
  ["Claims", "Compliance", "Legal", "Actuarial", "Operations", "Finance", "IT", "HR", "Executive", "Underwriting"]
- "checklist": array of 2-4 specific action items (strings). What exactly should the compliance team DO?
  Be specific: not "review the rule" but "Update third-party vendor agreements to include new data sharing restrictions by June 30"
- "deadline": string or null. Specific date if mentioned, otherwise null.
- "impact": one sentence. What is the direct business impact for a US insurer or bank?
- "confidence": "high", "medium", or "low" — how confident are you in this analysis given the information provided?

IMPORTANT:
- If you cannot determine a field with confidence, set it to null rather than guessing
- For "checklist", only include items that are clearly required by the regulation — do not add generic advice
- Mark confidence as "low" if only a title is available with no abstract

Return ONLY a valid JSON array. No markdown. No explanation. Just the array.

Publications:
{pub_text}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        raw = raw.replace("```json","").replace("```","").strip()
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

    except Exception as e:
        print(f"  ⚠️  Claude analysis error: {e}")
        for pub in publications:
            pub.setdefault("urgency", "INFORMATIONAL")
            pub.setdefault("summary", f"New publication from {pub.get('source','unknown')}. Manual review required.")
            pub.setdefault("teams", "Compliance")
            pub.setdefault("checklist", ["Review publication manually", "Assess applicability to your operations"])
            pub.setdefault("confidence", "low")

    return publications


def generate_digest_summary(publications: list[dict]) -> str:
    """Generates a high-level narrative summary of today's digest."""
    if not publications:
        return "No new regulatory publications today."

    urgent   = [p for p in publications if p.get("urgency") == "URGENT"]
    monitor  = [p for p in publications if p.get("urgency") == "MONITOR"]
    info     = [p for p in publications if p.get("urgency") == "INFORMATIONAL"]

    items_text = ""
    for p in publications[:20]:
        items_text += f"- [{p['urgency']}] {p['source']}: {p['title']}\n"
        if p.get("summary"):
            items_text += f"  {p['summary']}\n"

    prompt = f"""Write a brief executive summary (4-6 sentences) of today's regulatory activity for a US insurance and banking compliance team.

Today's publications:
{items_text}

Stats: {len(urgent)} urgent, {len(monitor)} to monitor, {len(info)} informational.

Be direct. Mention the most important items by name. State clearly if any require immediate action.
Do not use bullet points — write in flowing prose.
End with one sentence on the overall compliance risk level for the week."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠️  Summary generation error: {e}")
        return f"Today's digest contains {len(publications)} new publications including {len(urgent)} urgent items requiring immediate attention."
