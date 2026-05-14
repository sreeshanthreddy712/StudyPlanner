"""
Database models and helper functions for SmartPrep AI.

Using raw SQLite here instead of an ORM to keep things lightweight
and transparent — easier to debug, easier to demo.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    """Open a connection with row_factory so we get dict-like rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables on first run. Safe to call multiple times."""
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS study_plans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            exam_date   TEXT NOT NULL,          -- ISO date string
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id     INTEGER NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
            name        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            difficulty  TEXT NOT NULL CHECK(difficulty IN ('Easy', 'Medium', 'Hard')),
            weight      REAL NOT NULL           -- pre-computed from difficulty
        );

        CREATE TABLE IF NOT EXISTS schedule_slots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id     INTEGER NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
            topic_id    INTEGER NOT NULL REFERENCES topics(id),
            slot_date   TEXT NOT NULL,          -- ISO date string
            duration_hr REAL NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'complete', 'incomplete'))
        );
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Plan helpers
# ---------------------------------------------------------------------------

def create_plan(name: str, exam_date: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO study_plans (name, exam_date, created_at) VALUES (?, ?, ?)",
        (name, exam_date, datetime.now().isoformat())
    )
    plan_id = cur.lastrowid
    conn.commit()
    conn.close()
    return plan_id


def get_plan(plan_id: int):
    conn = get_db()
    plan = conn.execute(
        "SELECT * FROM study_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    conn.close()
    return dict(plan) if plan else None


def list_plans():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM study_plans ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_plan(plan_id: int):
    conn = get_db()
    conn.execute("DELETE FROM study_plans WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Subject / topic helpers
# ---------------------------------------------------------------------------

DIFFICULTY_WEIGHT = {"Easy": 1.0, "Medium": 1.5, "Hard": 2.0}


def add_subject_with_topics(plan_id: int, subject_name: str, topics: list) -> int:
    """
    topics: [{"name": str, "difficulty": str}, ...]
    Returns the new subject id.
    """
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO subjects (plan_id, name) VALUES (?, ?)",
        (plan_id, subject_name)
    )
    subject_id = cur.lastrowid

    for t in topics:
        weight = DIFFICULTY_WEIGHT.get(t["difficulty"], 1.0)
        conn.execute(
            "INSERT INTO topics (subject_id, name, difficulty, weight) VALUES (?, ?, ?, ?)",
            (subject_id, t["name"], t["difficulty"], weight)
        )

    conn.commit()
    conn.close()
    return subject_id


def get_topics_for_plan(plan_id: int) -> list:
    """
    Returns all topics joined with their subject name.
    Used by the scheduler to build the full topic list.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT t.id, t.name, t.difficulty, t.weight,
               s.id AS subject_id, s.name AS subject_name
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        WHERE s.plan_id = ?
    """, (plan_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schedule slot helpers
# ---------------------------------------------------------------------------

def save_schedule(plan_id: int, slots: list):
    """
    slots: [{"topic_id": int, "slot_date": str, "duration_hr": float}, ...]
    Clears any previous schedule for this plan before inserting.
    """
    conn = get_db()
    conn.execute("DELETE FROM schedule_slots WHERE plan_id = ?", (plan_id,))
    conn.executemany(
        "INSERT INTO schedule_slots (plan_id, topic_id, slot_date, duration_hr) VALUES (?, ?, ?, ?)",
        [(plan_id, s["topic_id"], s["slot_date"], s["duration_hr"]) for s in slots]
    )
    conn.commit()
    conn.close()


def get_schedule(plan_id: int) -> list:
    """Fetch all slots with topic/subject info, sorted by date."""
    conn = get_db()
    rows = conn.execute("""
        SELECT ss.id, ss.slot_date, ss.duration_hr, ss.status,
               t.name AS topic_name, t.difficulty,
               s.name AS subject_name
        FROM schedule_slots ss
        JOIN topics t ON ss.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE ss.plan_id = ?
        ORDER BY ss.slot_date ASC, s.name ASC
    """, (plan_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_slot_status(slot_id: int, status: str):
    conn = get_db()
    conn.execute(
        "UPDATE schedule_slots SET status = ? WHERE id = ?",
        (status, slot_id)
    )
    conn.commit()
    conn.close()


def get_slot(slot_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM schedule_slots WHERE id = ?", (slot_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Stats / dashboard helpers
# ---------------------------------------------------------------------------

def get_progress_stats(plan_id: int) -> dict:
    """Aggregate completion data per subject and overall."""
    conn = get_db()

    overall = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) AS done
        FROM schedule_slots
        WHERE plan_id = ?
    """, (plan_id,)).fetchone()

    by_subject = conn.execute("""
        SELECT s.name AS subject_name,
               COUNT(*) AS total,
               SUM(CASE WHEN ss.status = 'complete' THEN 1 ELSE 0 END) AS done
        FROM schedule_slots ss
        JOIN topics t ON ss.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE ss.plan_id = ?
        GROUP BY s.id
    """, (plan_id,)).fetchall()

    # Streak: consecutive days ending today that have at least one completion
    streak_rows = conn.execute("""
        SELECT DISTINCT slot_date
        FROM schedule_slots
        WHERE plan_id = ? AND status = 'complete'
        ORDER BY slot_date DESC
    """, (plan_id,)).fetchall()

    conn.close()

    total = overall["total"] or 0
    done = overall["done"] or 0
    pct = round((done / total * 100) if total else 0, 1)

    subjects_stats = []
    for row in by_subject:
        t = row["total"] or 0
        d = row["done"] or 0
        subjects_stats.append({
            "subject": row["subject_name"],
            "total": t,
            "done": d,
            "pct": round((d / t * 100) if t else 0, 1)
        })

    streak = _calc_streak([r["slot_date"] for r in streak_rows])

    return {
        "total_slots": total,
        "completed": done,
        "overall_pct": pct,
        "subjects": subjects_stats,
        "streak": streak,
    }


def _calc_streak(completed_dates: list) -> int:
    """
    Count consecutive completed days going backwards from today.
    A streak breaks the moment we hit a day with no completions.
    """
    from datetime import date, timedelta

    if not completed_dates:
        return 0

    date_set = set(completed_dates)
    today = date.today()
    streak = 0
    cursor = today

    while cursor.isoformat() in date_set:
        streak += 1
        cursor -= timedelta(days=1)

    return streak
