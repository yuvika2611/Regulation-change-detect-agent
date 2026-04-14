# ComplianceAI — Full Platform

Regulatory monitoring + human review + action checklists + audit trail
+ client management + Slack + email digest. Built for US banking & insurance.

---

## Project Structure

```
complianceai/
├── agents/
│   ├── scraper.py        ← Fetches 7 regulatory sources
│   ├── analyzer.py       ← Claude AI: summary, urgency, checklists
│   ├── notifier.py       ← Email (SendGrid) + Slack notifications
│   ├── orchestrator.py   ← Main pipeline + human review functions
│   └── scheduler.py      ← Runs daily at 7am
├── backend/
│   └── main.py           ← FastAPI REST API (all endpoints)
├── database/
│   └── db.py             ← SQLite database (all tables)
├── frontend/
│   └── index.html        ← Full React dashboard
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup (15 minutes)

### 1. Install Python 3.11
https://python.org — check "Add to PATH" during Windows install

### 2. Get API keys
- Anthropic: https://console.anthropic.com → API Keys
- SendGrid: https://sendgrid.com → Settings → API Keys → Full Access
  (Also verify your FROM_EMAIL in Sender Authentication)
- Slack webhook (optional): https://api.slack.com/apps → create app → Incoming Webhooks

### 3. Install and configure
```bash
pip install -r requirements.txt
cp .env.example .env
# Open .env and fill in your API keys
```

### 4. Run

**Option A — Just the agent (simplest start):**
```bash
python agents/orchestrator.py
```
Fetches everything, analyzes with Claude, sends email. Done.

**Option B — Full platform:**
```bash
# Terminal 1: API server
uvicorn backend.main:app --reload --port 8000

# Terminal 2: Daily scheduler
python agents/scheduler.py

# Open in browser:
open frontend/index.html
# OR visit: http://localhost:8000/dashboard
```

---

## What Each File Does

| File | Purpose |
|------|---------|
| `scraper.py` | Hits OCC, FinCEN, NAIC, Federal Register, SEC, CA DOI, NYDFS |
| `analyzer.py` | Sends to Claude → returns summary, urgency, team checklist, deadline |
| `notifier.py` | Formats email HTML, sends via SendGrid, sends Slack alerts |
| `orchestrator.py` | Full pipeline + human review queue functions |
| `scheduler.py` | Runs `run_daily_check()` at 7am every day |
| `backend/main.py` | REST API: publications, reviews, clients, checklists, audit, stats |
| `database/db.py` | All tables: publications, reviews, audit_trail, clients, checklists |
| `frontend/index.html` | Dashboard: all 6 tabs, works with or without backend |

---

## The 3 Problems It Solves (vs basic version)

### Problem 1 — Accuracy (Human Review Queue)
- Low/medium AI confidence → auto-tagged as "pending review"
- Review Queue tab shows all pending items
- Reviewer can: approve, reject, or correct the analysis
- Every correction saved to database and applied before sending to clients
- API: POST /api/reviews/{pub_id}

### Problem 2 — Trust (Audit Trail)
- Every action logged: fetch, analysis, review, email sent, client added
- Audit Trail tab shows full history with timestamps
- API: GET /api/audit
- This is what you show enterprise clients during procurement review

### Problem 3 — Integration
- Slack: urgent items sent immediately to Slack webhook
- Per-client Slack webhooks (each client gets their own channel)
- Email: professional HTML digest with urgency stats, checklists, links
- Action checklists: team-specific tasks generated per publication

---

## Deploy to Production

### Railway.app ($5/month — easiest)
```bash
# Push to GitHub first
git init && git add . && git commit -m "ComplianceAI v1"
git remote add origin https://github.com/YOURNAME/complianceai.git
git push -u origin main
```
1. railway.app → New Project → Deploy from GitHub
2. Add environment variables from your .env
3. Done — runs 24/7 automatically

### Upgrade to PostgreSQL (when you have 5+ clients)
Change in db.py:
```python
import psycopg2
DATABASE_URL = os.getenv("DATABASE_URL")  # set in Railway dashboard
```

---

## Pricing

| Plan | Price | Features |
|------|-------|----------|
| Starter | $10,000/year | 7 sources, email digest, 1 user |
| Professional | $20,000/year | + Slack, dashboard, 5 users, review queue |
| Enterprise | $40,000/year | + API access, custom sources, training video add-on |

ARR targets: 5 clients = $100K | 20 clients = $400K | 50 clients = $1M

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/stats | Dashboard stats |
| GET | /api/publications | All publications (filterable) |
| GET | /api/publications/{id} | Single publication with checklists + reviews |
| POST | /api/run-check | Trigger manual check |
| GET | /api/reviews/pending | Publications needing human review |
| POST | /api/reviews/{pub_id} | Submit review decision |
| GET | /api/checklists | All action items (filter by team) |
| PATCH | /api/checklists/{id}/complete | Mark item complete |
| GET | /api/audit | Full audit trail |
| GET | /api/digests | All digest records |
| GET | /api/clients | All clients |
| POST | /api/clients | Add client |
| PATCH | /api/clients/{id} | Update client |

Interactive docs: http://localhost:8000/docs

---

## Roadmap

v1.0 (now): Monitoring + review + checklists + audit + email + Slack
v1.5 (month 3): Add compliance training script generation per regulation change
v2.0 (month 6): Add video generation (Synthesia API) + Workday LMS push
v3.0 (month 12): Full loop — regulation → video → certified employee → audit report

Built with Python · FastAPI · Claude AI · SQLite · SendGrid · React
