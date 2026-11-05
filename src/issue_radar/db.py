import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".issue-radar" / "issues.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id         INTEGER PRIMARY KEY,  -- GitHub's id for the issue
    repo       TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    stars      INTEGER NOT NULL,
    language   TEXT NOT NULL,
    created_at TEXT NOT NULL,        -- when the issue was opened on GitHub
    found_at   TEXT NOT NULL,        -- when we first saw it
    status     TEXT NOT NULL DEFAULT 'new'  -- new | interested | skipped
);

CREATE TABLE IF NOT EXISTS blocked_repos (
    repo TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    # Wait up to 10 s if the scanner is writing at the same moment.
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_issues(conn: sqlite3.Connection, issues: list[dict], language: str) -> list[dict]:
    """Save issues we haven't seen before and return only the new ones."""
    now = datetime.now(timezone.utc).isoformat()
    new_issues = []
    for issue in issues:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO issues (id, repo, title, url, stars, language, created_at, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue["id"],
                issue["repo"],
                issue["title"],
                issue["html_url"],
                issue["stars"],
                language,
                issue["created_at"],
                now,
            ),
        )
        if cursor.rowcount == 1:
            new_issues.append(issue)
    return new_issues


def list_issues(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM issues
        WHERE status = ? AND repo NOT IN (SELECT repo FROM blocked_repos)
        ORDER BY created_at DESC
        """,
        (status,),
    ).fetchall()


def get_issue(conn: sqlite3.Connection, issue_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()


def set_status(conn: sqlite3.Connection, issue_id: int, status: str) -> None:
    conn.execute("UPDATE issues SET status = ? WHERE id = ?", (status, issue_id))


def block_repo(conn: sqlite3.Connection, repo: str) -> None:
    conn.execute("INSERT OR IGNORE INTO blocked_repos (repo) VALUES (?)", (repo,))


def unblock_repo(conn: sqlite3.Connection, repo: str) -> None:
    conn.execute("DELETE FROM blocked_repos WHERE repo = ?", (repo,))


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def list_blocked_repos(conn: sqlite3.Connection) -> list[str]:
    return [row["repo"] for row in conn.execute("SELECT repo FROM blocked_repos ORDER BY repo")]
