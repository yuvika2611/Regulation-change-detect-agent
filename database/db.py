"""
Database — SQLite for dev, swap DATABASE_URL to PostgreSQL for production.
All tables: publications, digests, clients, audit_trail, reviews, notifications, users
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "complianceai.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS publications (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        pub_id       TEXT UNIQUE NOT NULL,
        source       TEXT NOT NULL,
        title        TEXT NOT NULL,
        url          TEXT,
        pub_type     TEXT,
        abstract     TEXT,
        agency       TEXT,
        urgency      TEXT DEFAULT 'INFORMATIONAL',
        summary      TEXT,
        teams        TEXT,
        deadline     TEXT,
        impact       TEXT,
        is_new       INTEGER DEFAULT 1,
        review_status TEXT DEFAULT 'pending',
        reviewed_by  TEXT,
        reviewed_at  TEXT,
        fetched_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS seen_publications (
        pub_id  TEXT PRIMARY KEY,
        seen_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS reviews (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        pub_id       TEXT NOT NULL,
        reviewer     TEXT NOT NULL,
        decision     TEXT NOT NULL,
        notes        TEXT,
        corrected_summary TEXT,
        corrected_urgency TEXT,
        corrected_teams   TEXT,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS audit_trail (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        pub_id     TEXT,
        client_id  INTEGER,
        actor      TEXT,
        details    TEXT,
        ip_address TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS digests (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        pub_count     INTEGER,
        summary       TEXT,
        urgent_count  INTEGER DEFAULT 0,
        monitor_count INTEGER DEFAULT 0,
        info_count    INTEGER DEFAULT 0,
        email_sent    INTEGER DEFAULT 0,
        slack_sent    INTEGER DEFAULT 0,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS clients (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name   TEXT NOT NULL,
        contact_name   TEXT,
        contact_email  TEXT,
        plan           TEXT DEFAULT 'starter',
        industry       TEXT DEFAULT 'insurance',
        notes          TEXT,
        status         TEXT DEFAULT 'active',
        annual_value   REAL DEFAULT 10000,
        slack_webhook  TEXT,
        custom_sources TEXT,
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
        renewal_date   TEXT
    );

    CREATE TABLE IF NOT EXISTS checklists (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        pub_id       TEXT NOT NULL,
        client_id    INTEGER,
        team         TEXT NOT NULL,
        item         TEXT NOT NULL,
        completed    INTEGER DEFAULT 0,
        completed_by TEXT,
        completed_at TEXT,
        due_date     TEXT,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id    INTEGER,
        pub_id       TEXT,
        channel      TEXT NOT NULL,
        status       TEXT DEFAULT 'pending',
        sent_at      TEXT,
        error        TEXT,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()
    print("✅ All database tables ready")

def log_audit(event_type: str, pub_id: str = None, client_id: int = None,
              actor: str = "system", details: str = None):
    db = get_db()
    db.execute(
        """INSERT INTO audit_trail (event_type, pub_id, client_id, actor, details)
           VALUES (?,?,?,?,?)""",
        (event_type, pub_id, client_id, actor, details)
    )
    db.commit()
