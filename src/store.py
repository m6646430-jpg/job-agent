"""SQLite store: every job seen, scored, applied, or skipped — the audit trail."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,      -- source:external_id
    source      TEXT,                  -- greenhouse | lever | ashby | remotive
    company     TEXT,
    title       TEXT,
    location    TEXT,
    url         TEXT,
    apply_url   TEXT,
    jd_text     TEXT,
    score       INTEGER,
    score_reason TEXT,
    status      TEXT DEFAULT 'seen',   -- seen | scored | skipped | queued | applied | failed | captcha
    status_note TEXT,
    first_seen  TEXT,
    updated_at  TEXT
);
"""


class Store:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)   # data/ is not in the repo
        self.db = sqlite3.connect(DB_PATH)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def seen(self, job_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone() is not None

    def add_job(self, job: dict):
        now = datetime.now().isoformat(timespec="seconds")
        self.db.execute(
            "INSERT OR IGNORE INTO jobs (job_id, source, company, title, location, url, apply_url, jd_text, first_seen, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job["job_id"], job["source"], job["company"], job["title"],
             job.get("location", ""), job.get("url", ""), job.get("apply_url", ""),
             job.get("jd_text", ""), now, now),
        )
        self.db.commit()

    def set_score(self, job_id: str, score: int, reason: str):
        self.db.execute(
            "UPDATE jobs SET score=?, score_reason=?, status='scored', updated_at=? WHERE job_id=?",
            (score, reason, datetime.now().isoformat(timespec="seconds"), job_id),
        )
        self.db.commit()

    def set_status(self, job_id: str, status: str, note: str = ""):
        self.db.execute(
            "UPDATE jobs SET status=?, status_note=?, updated_at=? WHERE job_id=?",
            (status, note, datetime.now().isoformat(timespec="seconds"), job_id),
        )
        self.db.commit()

    def unscored(self) -> list:
        return self.db.execute("SELECT * FROM jobs WHERE status='seen' ORDER BY first_seen").fetchall()

    def apply_candidates(self, min_score: int, limit: int) -> list:
        return self.db.execute(
            "SELECT * FROM jobs WHERE status='scored' AND score>=? ORDER BY score DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()

    def report(self) -> list:
        return self.db.execute(
            "SELECT status, COUNT(*) n FROM jobs GROUP BY status ORDER BY n DESC"
        ).fetchall()
