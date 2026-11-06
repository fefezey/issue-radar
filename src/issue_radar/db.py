import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
    -- Later additions are in ADDED_ISSUE_COLUMNS below.
);

CREATE TABLE IF NOT EXISTS blocked_repos (
    repo TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Projects you've opened pull requests in, refreshed once a day.
CREATE TABLE IF NOT EXISTS contributions (
    repo          TEXT PRIMARY KEY,
    pull_requests INTEGER NOT NULL
);

-- Star counts we already looked up, so we don't ask GitHub again every scan.
CREATE TABLE IF NOT EXISTS repo_stars (
    repo       TEXT PRIMARY KEY,
    stars      INTEGER NOT NULL,
    checked_at TEXT NOT NULL
);
"""


# Columns added to `issues` after the first release. Databases created
# earlier get them on the next start, without losing any data.
ADDED_ISSUE_COLUMNS = {
    "body": "TEXT",  # the issue's description, shortened
    "summary": "TEXT",  # AI summary
    "summary_lang": "TEXT",  # language the summary is written in
    "summary_version": "INTEGER",  # which version of the AI instructions wrote it
    "difficulty": "TEXT",  # no longer used: small models couldn't judge difficulty (see kinds.py)
    "effort": "TEXT",  # no longer used: small models couldn't estimate time
    "availability": "TEXT",  # open | taken | closed, from the last check on GitHub
    "checked_at": "TEXT",  # when we last checked that
    "labels": "TEXT",  # the issue's GitHub labels, as a JSON list
    "stage": "TEXT",  # for interested issues: commented | assigned | pr_open | merged
    "stage_changed_at": "TEXT",
    "pr_url": "TEXT",  # your pull request for it, if any
    "explanation": "TEXT",  # the issue guide's plain explanation (AI), once made
    "explanation_lang": "TEXT",
}

# Issues that are no longer free on GitHub are dropped from "new".
_STILL_FREE = "COALESCE(availability, 'open') = 'open'"

BODY_MAX_LENGTH = 4000


# Columns added to `repo_stars` later: what the project is, and whether it
# merges pull requests from outside its team.
ADDED_REPO_COLUMNS = {
    "description": "TEXT",
    "outside_merged": "INTEGER",  # merged pull requests from outsiders, last 90 days
    "info_checked_at": "TEXT",
    "claim_policy": "TEXT",  # "ask" or "no_claim", from the contributing guide
    "guide_checked_at": "TEXT",
}


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, columns in (("issues", ADDED_ISSUE_COLUMNS), ("repo_stars", ADDED_REPO_COLUMNS)):
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


@contextmanager
def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    # Wait up to 10 s if the scanner is writing at the same moment.
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
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
            INSERT OR IGNORE INTO issues
                (id, repo, title, url, stars, language, created_at, found_at, body, availability, checked_at, labels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
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
                (issue.get("body") or "")[:BODY_MAX_LENGTH],
                now,  # the search just checked that nobody has taken it
                json.dumps([label["name"] for label in issue.get("labels", [])]),
            ),
        )
        if cursor.rowcount == 1:
            new_issues.append(issue)
    return new_issues


def list_issues(
    conn: sqlite3.Connection,
    status: str,
    languages: list[str] | None = None,
    min_stars: int = 0,
) -> list[sqlite3.Row]:
    """Issues with this status, newest first, skipping hidden projects.

    `languages` and `min_stars` narrow the list, so changing the settings
    takes effect right away, before the next scan.
    """
    query = """
        SELECT * FROM issues
        WHERE status = ? AND stars >= ? AND repo NOT IN (SELECT repo FROM blocked_repos)
    """
    if status == "new":
        query += f" AND {_STILL_FREE}"
    params: list = [status, min_stars]
    if languages is not None:
        query += f" AND language IN ({', '.join('?' * len(languages))})"
        params += languages
    return conn.execute(query + " ORDER BY created_at DESC", params).fetchall()


def get_issue(conn: sqlite3.Connection, issue_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()


def issues_to_summarize(conn: sqlite3.Connection, lang: str, version: int, limit: int) -> list[sqlite3.Row]:
    """Issues without an up-to-date summary in `lang`, newest first, skipping hidden projects."""
    return conn.execute(
        f"""
        SELECT * FROM issues
        WHERE (status = 'interested' OR (status = 'new' AND {_STILL_FREE}))
          AND (summary IS NULL OR summary_lang IS NOT ? OR COALESCE(summary_version, 1) < ?)
          AND repo NOT IN (SELECT repo FROM blocked_repos)
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (lang, version, limit),
    ).fetchall()


def issues_to_recheck(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Issues still shown as free, the ones checked longest ago first."""
    return conn.execute(
        f"""
        SELECT id, url, title, status FROM issues
        WHERE status IN ('new', 'interested') AND {_STILL_FREE}
        ORDER BY labels IS NOT NULL, checked_at IS NOT NULL, checked_at
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def issues_to_track(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Issues you're interested in, to follow how far you've got."""
    return conn.execute(
        "SELECT id, url, title, stage FROM issues WHERE status = 'interested' ORDER BY found_at DESC LIMIT ?",
        (limit,),
    ).fetchall()


def save_progress(conn: sqlite3.Connection, issue_id: int, stage: str | None, pr_url: str | None) -> None:
    """Save where you are with an issue; remember when that last changed."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE issues
        SET stage_changed_at = CASE WHEN stage IS ? THEN COALESCE(stage_changed_at, ?) ELSE ? END,
            stage = ?, pr_url = ?
        WHERE id = ?
        """,
        (stage, now, now, stage, pr_url, issue_id),
    )


def set_availability(conn: sqlite3.Connection, results: dict[int, str], labels: dict[int, list[str]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE issues SET availability = ?, checked_at = ? WHERE id = ?",
        [(availability, now, issue_id) for issue_id, availability in results.items()],
    )
    conn.executemany(
        "UPDATE issues SET labels = ? WHERE id = ?",
        [(json.dumps(names), issue_id) for issue_id, names in labels.items()],
    )


def set_body(conn: sqlite3.Connection, issue_id: int, body: str) -> None:
    conn.execute("UPDATE issues SET body = ? WHERE id = ?", (body[:BODY_MAX_LENGTH], issue_id))


def save_summary(
    conn: sqlite3.Connection, issue_id: int, summary: str, lang: str, version: int
) -> None:
    """Save the AI's answer. An empty summary means "nothing worth showing"."""
    conn.execute(
        """
        UPDATE issues
        SET summary = ?, difficulty = NULL, effort = NULL, summary_lang = ?, summary_version = ?
        WHERE id = ?
        """,
        (summary, lang, version, issue_id),
    )


def save_explanation(conn: sqlite3.Connection, issue_id: int, text: str, lang: str) -> None:
    conn.execute("UPDATE issues SET explanation = ?, explanation_lang = ? WHERE id = ?", (text, lang, issue_id))


def set_status(conn: sqlite3.Connection, issue_id: int, status: str) -> None:
    conn.execute("UPDATE issues SET status = ? WHERE id = ?", (status, issue_id))


def block_repo(conn: sqlite3.Connection, repo: str) -> None:
    conn.execute("INSERT OR IGNORE INTO blocked_repos (repo) VALUES (?)", (repo,))


def unblock_repo(conn: sqlite3.Connection, repo: str) -> None:
    conn.execute("DELETE FROM blocked_repos WHERE repo = ?", (repo,))


def load_repo_stars(conn: sqlite3.Connection, max_age: timedelta) -> dict[str, int]:
    """Star counts looked up within `max_age`."""
    since = (datetime.now(timezone.utc) - max_age).isoformat()
    rows = conn.execute("SELECT repo, stars FROM repo_stars WHERE checked_at >= ?", (since,))
    return {row["repo"]: row["stars"] for row in rows}


def repos_needing_info(conn: sqlite3.Connection, max_age: timedelta, limit: int) -> list[str]:
    """Projects with issues on the list whose info is missing or older than `max_age`."""
    since = (datetime.now(timezone.utc) - max_age).isoformat()
    rows = conn.execute(
        f"""
        SELECT DISTINCT i.repo FROM issues i
        LEFT JOIN repo_stars r ON r.repo = i.repo
        WHERE i.status IN ('new', 'interested') AND {_STILL_FREE}
          AND i.repo NOT IN (SELECT repo FROM blocked_repos)
          AND (r.info_checked_at IS NULL OR r.info_checked_at < ?)
        LIMIT ?
        """,
        (since, limit),
    )
    return [row["repo"] for row in rows]


def save_repo_info(conn: sqlite3.Connection, repo: str, info: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO repo_stars (repo, stars, checked_at, description, outside_merged, info_checked_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(repo) DO UPDATE SET
            stars = excluded.stars, checked_at = excluded.checked_at,
            description = excluded.description, outside_merged = excluded.outside_merged,
            info_checked_at = excluded.info_checked_at
        """,
        (repo, info["stars"], now, info["description"], info["outside_merged"], now),
    )


def get_claim_policy(conn: sqlite3.Connection, repo: str, max_age: timedelta) -> str | None:
    """What the project's contributing guide says about claiming, if we read it within `max_age`."""
    since = (datetime.now(timezone.utc) - max_age).isoformat()
    row = conn.execute(
        "SELECT claim_policy FROM repo_stars WHERE repo = ? AND guide_checked_at >= ?", (repo, since)
    ).fetchone()
    return row["claim_policy"] if row else None


def save_claim_policy(conn: sqlite3.Connection, repo: str, policy: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO repo_stars (repo, stars, checked_at, claim_policy, guide_checked_at)
        VALUES (?, 0, '', ?, ?)
        ON CONFLICT(repo) DO UPDATE SET claim_policy = excluded.claim_policy, guide_checked_at = excluded.guide_checked_at
        """,
        (repo, policy, now),
    )


def load_repo_info(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Project info we have, by repository name."""
    rows = conn.execute("SELECT * FROM repo_stars WHERE info_checked_at IS NOT NULL")
    return {row["repo"]: row for row in rows}


def save_repo_stars(conn: sqlite3.Connection, stars: dict[str, int]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO repo_stars (repo, stars, checked_at) VALUES (?, ?, ?)
        ON CONFLICT(repo) DO UPDATE SET stars = excluded.stars, checked_at = excluded.checked_at
        """,
        [(repo, count, now) for repo, count in stars.items()],
    )


def save_contributions(conn: sqlite3.Connection, counts: dict[str, int]) -> None:
    """Replace the list of projects you've contributed to."""
    conn.execute("DELETE FROM contributions")
    conn.executemany("INSERT INTO contributions (repo, pull_requests) VALUES (?, ?)", counts.items())
    set_setting(conn, "contributions_checked_at", datetime.now(timezone.utc).isoformat())


def contributions_checked_at(conn: sqlite3.Connection) -> datetime | None:
    checked = get_setting(conn, "contributions_checked_at")
    return datetime.fromisoformat(checked) if checked else None


def load_contributions(conn: sqlite3.Connection) -> dict[str, int] | None:
    """Projects you've contributed to and how many pull requests you opened in each,
    or None if we haven't been able to check yet."""
    if contributions_checked_at(conn) is None:
        return None
    return {row["repo"]: row["pull_requests"] for row in conn.execute("SELECT * FROM contributions")}


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
