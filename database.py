"""
database.py — All SQLite setup and queries for the AI Python Learning Platform.
Creates the database automatically on first run and (optionally) seeds demo accounts.
"""

import hashlib
import hmac
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import config

DB_PATH = config.DB_PATH

# Password hashing: salted PBKDF2-HMAC-SHA256 (Python standard library).
# Stored format: "pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>".
# Hashes created by earlier versions (plain SHA-256 hex) are still accepted and
# are transparently upgraded to the new format on the next successful login.
_PBKDF2_ITERATIONS = 260_000
_HASH_PREFIX = "pbkdf2_sha256"


@contextmanager
def _connect():
    """Yield a connection that commits on success and always closes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_connection():
    """Get a raw connection to the SQLite database (caller must close it)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{_HASH_PREFIX}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _is_legacy_hash(stored: str) -> bool:
    return not stored.startswith(_HASH_PREFIX + "$")


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash (new or legacy format)."""
    if _is_legacy_hash(stored):
        candidate = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(candidate, stored)
    try:
        _, iterations, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# ── Schema ───────────────────────────────────────────────────────────────────

def initialize_database():
    """Create tables and seed demo accounts on first run."""
    with _connect() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('instructor', 'learner')),
                full_name TEXT DEFAULT ''
            )
        """)

        # Graceful migration: add full_name column for databases created before it existed
        columns = {row["name"] for row in cursor.execute("PRAGMA table_info(users)")}
        if "full_name" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                problem_statement TEXT NOT NULL,
                created_by TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                learner_username TEXT NOT NULL,
                question_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                feedback TEXT,
                hint_count INTEGER DEFAULT 0,
                flagged_ai INTEGER DEFAULT 0,
                keystroke_count INTEGER DEFAULT 0,
                char_count INTEGER DEFAULT 0,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id)
            )
        """)

        if config.SEED_DEMO_ACCOUNTS:
            demo_accounts = [
                ("instructor", "admin123", "instructor", "Demo Instructor"),
                ("learner1", "learn123", "learner", "Demo Learner"),
            ]
            for username, password, role, full_name in demo_accounts:
                cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,))
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                        (username, hash_password(password), role, full_name)
                    )


# ── Users ────────────────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str):
    """
    Authenticate a user by username and password.
    Returns a dict with user info on success, None on failure.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password, role, full_name FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        if row is None or not verify_password(password, row["password"]):
            return None
        if _is_legacy_hash(row["password"]):
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (hash_password(password), row["id"])
            )
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "full_name": row["full_name"] or "",
        }


def check_username_exists(username: str) -> bool:
    """Check if a username already exists in the database."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username,)).fetchone()
        return row[0] > 0


def register_user(full_name: str, username: str, password: str) -> bool:
    """
    Register a new learner account.
    Returns True on success, False if username already taken.
    """
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), "learner", full_name)
            )
        return True
    except sqlite3.IntegrityError:
        return False


# ── Questions ────────────────────────────────────────────────────────────────

def add_question(title: str, problem_statement: str, created_by: str) -> int:
    """Insert a new question and return its id."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO questions (title, problem_statement, created_by) VALUES (?, ?, ?)",
            (title, problem_statement, created_by)
        )
        return cursor.lastrowid


def get_all_questions():
    """Retrieve all questions (newest first) with their submission counts."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT q.id, q.title, q.problem_statement, q.created_by,
                   COUNT(s.id) AS submission_count
            FROM questions q
            LEFT JOIN submissions s ON s.question_id = q.id
            GROUP BY q.id
            ORDER BY q.id DESC
        """).fetchall()
        return [dict(row) for row in rows]


def delete_question(question_id: int):
    """Delete a question and all its related submissions."""
    with _connect() as conn:
        conn.execute("DELETE FROM submissions WHERE question_id = ?", (question_id,))
        conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))


# ── Submissions ──────────────────────────────────────────────────────────────

def save_submission(learner_username: str, question_id: int, code: str, feedback,
                    hint_count: int, flagged_ai: int, keystroke_count: int,
                    char_count: int) -> int:
    """Save a learner's code submission and return its id.

    `feedback` may be None when the AI review has not finished yet; it can be
    filled in later with set_submission_feedback().
    """
    with _connect() as conn:
        cursor = conn.execute(
            """INSERT INTO submissions
               (learner_username, question_id, code, feedback, hint_count, flagged_ai,
                keystroke_count, char_count, submitted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (learner_username, question_id, code, feedback, hint_count, flagged_ai,
             keystroke_count, char_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        return cursor.lastrowid


def set_submission_feedback(submission_id: int, feedback: str):
    """Attach AI feedback to an existing submission."""
    with _connect() as conn:
        conn.execute("UPDATE submissions SET feedback = ? WHERE id = ?", (feedback, submission_id))


def get_all_submissions():
    """Retrieve all submissions with question titles and learner names for the instructor view."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT s.id, s.learner_username, COALESCE(u.full_name, '') AS learner_name,
                   q.title AS question_title, s.code, s.feedback,
                   s.hint_count, s.flagged_ai, s.keystroke_count, s.char_count, s.submitted_at
            FROM submissions s
            JOIN questions q ON s.question_id = q.id
            LEFT JOIN users u ON u.username = s.learner_username
            ORDER BY s.submitted_at DESC, s.id DESC
        """).fetchall()
        return [dict(row) for row in rows]


def get_submitted_question_ids(learner_username: str) -> set:
    """Return the ids of questions the learner has submitted at least once."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT question_id FROM submissions WHERE learner_username = ?",
            (learner_username,)
        ).fetchall()
        return {row[0] for row in rows}
