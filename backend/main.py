"""
ComplianceAI — FastAPI Backend
================================
All API endpoints. Run: uvicorn backend.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db     import get_db, init_db, log_audit
from agents.orchestrator import run_daily_check, get_pending_reviews, submit_review

app = FastAPI(title="ComplianceAI API", version="1.0.0",
              description="Regulatory monitoring + compliance automation for banking & insurance")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup(): init_db()

# ── Health ────────────────────────────────────
@app.get("/")
def root():
    return {"status":"ok","product":"ComplianceAI","version":"1.0.0",
            "docs":"/docs","dashboard":"/dashboard"}

# ── Dashboard (serves HTML) ───────────────────
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "../frontend/index.html")
    if os.path.exists(html_path):
        return open(html_path).read()
    return "<h1>Dashboard not built yet — run: python frontend/build.py</h1>"

# ── Publications ──────────────────────────────
@app.get("/api/publications")
def get_publications(
    limit:   int = Query(50, le=200),
    source:  Optional[str] = None,
    urgency: Optional[str] = None,
    review_status: Optional[str] = None,
):
    db = get_db()
    query = "SELECT * FROM publications WHERE 1=1"
    params = []
    if source:  query += " AND source=?";         params.append(source)
    if urgency: query += " AND urgency=?";         params.append(urgency)
    if review_status: query += " AND review_status=?"; params.append(review_status)
    query += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/publications/{pub_id}")
def get_publication(pub_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM publications WHERE pub_id=?", (pub_id,)).fetchone()
    if not row: raise HTTPException(404, "Publication not found")
    pub = dict(row)
    # Attach checklists
    checklists = db.execute(
        "SELECT * FROM checklists WHERE pub_id=? ORDER BY team", (pub_id,)
    ).fetchall()
    pub["checklists"] = [dict(c) for c in checklists]
    # Attach reviews
    reviews = db.execute(
        "SELECT * FROM reviews WHERE pub_id=? ORDER BY created_at DESC", (pub_id,)
    ).fetchall()
    pub["reviews"] = [dict(r) for r in reviews]
    return pub

# ── Review Queue ──────────────────────────────
@app.get("/api/reviews/pending")
def pending_reviews():
    return get_pending_reviews()

class ReviewSubmit(BaseModel):
    reviewer:   str
    decision:   str   # approved | rejected | corrected
    notes:      Optional[str] = None
    corrected_summary:  Optional[str] = None
    corrected_urgency:  Optional[str] = None
    corrected_teams:    Optional[str] = None

@app.post("/api/reviews/{pub_id}")
def review_publication(pub_id: str, body: ReviewSubmit):
    if body.decision not in ("approved","rejected","corrected"):
        raise HTTPException(400, "decision must be: approved | rejected | corrected")
    corrections = {}
    if body.corrected_summary: corrections["summary"] = body.corrected_summary
    if body.corrected_urgency: corrections["urgency"] = body.corrected_urgency
    if body.corrected_teams:   corrections["teams"]   = body.corrected_teams
    return submit_review(pub_id, body.reviewer, body.decision, body.notes, corrections)

# ── Checklists ────────────────────────────────
@app.get("/api/checklists")
def get_checklists(team: Optional[str] = None, completed: Optional[bool] = None):
    db = get_db()
    query = "SELECT c.*, p.title as pub_title, p.source, p.urgency FROM checklists c JOIN publications p ON c.pub_id=p.pub_id WHERE 1=1"
    params = []
    if team: query += " AND c.team=?"; params.append(team)
    if completed is not None: query += " AND c.completed=?"; params.append(1 if completed else 0)
    query += " ORDER BY p.urgency DESC, c.created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]

@app.patch("/api/checklists/{item_id}/complete")
def complete_checklist_item(item_id: int, completed_by: str = "user"):
    db = get_db()
    db.execute(
        "UPDATE checklists SET completed=1, completed_by=?, completed_at=? WHERE id=?",
        (completed_by, datetime.now().isoformat(), item_id)
    )
    db.commit()
    log_audit("CHECKLIST_COMPLETED", actor=completed_by, details=f"item_id={item_id}")
    return {"status":"completed","item_id":item_id}

# ── Audit Trail ───────────────────────────────
@app.get("/api/audit")
def get_audit_trail(limit: int = Query(100, le=500), event_type: Optional[str] = None):
    db = get_db()
    if event_type:
        rows = db.execute(
            "SELECT * FROM audit_trail WHERE event_type=? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_trail ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

# ── Digests ───────────────────────────────────
@app.get("/api/digests")
def get_digests(limit: int = 30):
    db = get_db()
    rows = db.execute("SELECT * FROM digests ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/digests/latest")
def latest_digest():
    db = get_db()
    row = db.execute("SELECT * FROM digests ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row: raise HTTPException(404, "No digest yet — run a check first")
    return dict(row)

# ── Run Check ─────────────────────────────────
@app.post("/api/run-check")
def trigger_check(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_daily_check)
    return {"status":"started","message":"Regulatory check running in background. Check /api/digests/latest in ~2 minutes."}

# ── Stats ─────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    db = get_db()
    total_pubs    = db.execute("SELECT COUNT(*) FROM publications").fetchone()[0]
    urgent        = db.execute("SELECT COUNT(*) FROM publications WHERE urgency='URGENT'").fetchone()[0]
    pending_rev   = db.execute("SELECT COUNT(*) FROM publications WHERE review_status='pending'").fetchone()[0]
    total_clients = db.execute("SELECT COUNT(*) FROM clients WHERE status='active'").fetchone()[0]
    total_digests = db.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
    open_checklists = db.execute("SELECT COUNT(*) FROM checklists WHERE completed=0").fetchone()[0]
    total_arr     = db.execute("SELECT COALESCE(SUM(annual_value),0) FROM clients WHERE status='active'").fetchone()[0]
    by_source     = db.execute("SELECT source, COUNT(*) as count FROM publications GROUP BY source ORDER BY count DESC").fetchall()
    by_urgency    = db.execute("SELECT urgency, COUNT(*) as count FROM publications GROUP BY urgency").fetchall()
    return {
        "total_publications": total_pubs,
        "urgent_items":       urgent,
        "pending_reviews":    pending_rev,
        "active_clients":     total_clients,
        "total_digests":      total_digests,
        "open_checklists":    open_checklists,
        "total_arr":          total_arr,
        "by_source":          [dict(r) for r in by_source],
        "by_urgency":         [dict(r) for r in by_urgency],
        "last_updated":       datetime.now().isoformat(),
    }

# ── Clients ───────────────────────────────────
class ClientCreate(BaseModel):
    company_name:   str
    contact_name:   str
    contact_email:  str
    plan:           str = "starter"       # starter | professional | enterprise
    industry:       str = "insurance"     # insurance | banking | both
    annual_value:   float = 10000
    slack_webhook:  Optional[str] = None
    notes:          Optional[str] = None
    renewal_date:   Optional[str] = None

@app.get("/api/clients")
def get_clients():
    db = get_db()
    rows = db.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/api/clients")
def add_client(client: ClientCreate):
    db = get_db()
    db.execute("""
        INSERT INTO clients (company_name, contact_name, contact_email, plan, industry,
                             annual_value, slack_webhook, notes, renewal_date, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (client.company_name, client.contact_name, client.contact_email,
          client.plan, client.industry, client.annual_value,
          client.slack_webhook, client.notes, client.renewal_date,
          datetime.now().isoformat()))
    db.commit()
    log_audit("CLIENT_ADDED", actor="admin", details=f"company={client.company_name}")
    return {"status":"created","company":client.company_name}

@app.patch("/api/clients/{client_id}")
def update_client(client_id: int, updates: dict):
    db = get_db()
    allowed = {"contact_name","contact_email","plan","industry",
               "annual_value","slack_webhook","notes","status","renewal_date"}
    valid = {k:v for k,v in updates.items() if k in allowed}
    if not valid: raise HTTPException(400, "No valid fields to update")
    set_clause = ", ".join(f"{k}=?" for k in valid)
    db.execute(f"UPDATE clients SET {set_clause} WHERE id=?", list(valid.values()) + [client_id])
    db.commit()
    return {"status":"updated","client_id":client_id}

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int):
    db = get_db()
    db.execute("UPDATE clients SET status='inactive' WHERE id=?", (client_id,))
    db.commit()
    return {"status":"deactivated","client_id":client_id}
