"""The local database."""

import sqlite3
from datetime import datetime, timedelta, timezone

from conftest import make_issue
from issue_radar import db


def test_issues_are_saved_once():
    with db.connect() as conn:
        assert len(db.save_issues(conn, [make_issue(1), make_issue(2)], "python")) == 2
        assert [i["id"] for i in db.save_issues(conn, [make_issue(2), make_issue(3)], "python")] == [3]


def test_new_list_drops_taken_closed_hidden_and_filtered_issues():
    with db.connect() as conn:
        db.save_issues(conn, [make_issue(1), make_issue(2), make_issue(3), make_issue(4, repo="other/repo")], "python")
        db.save_issues(conn, [make_issue(5, stars=10)], "go")
        db.set_availability(conn, {2: "taken", 3: "closed"}, {})
        db.block_repo(conn, "other/repo")
        shown = [i["id"] for i in db.list_issues(conn, "new", ["python", "go"], min_stars=100)]
    assert shown == [1]


def test_interested_issues_stay_even_when_taken():
    with db.connect() as conn:
        db.save_issues(conn, [make_issue(1)], "python")
        db.set_status(conn, 1, "interested")
        db.set_availability(conn, {1: "taken"}, {})
        assert [i["id"] for i in db.list_issues(conn, "interested")] == [1]


def test_progress_remembers_when_the_stage_changed():
    with db.connect() as conn:
        db.save_issues(conn, [make_issue(1)], "python")
        db.save_progress(conn, 1, "commented", None)
        first = db.get_issue(conn, 1)["stage_changed_at"]
        db.save_progress(conn, 1, "commented", None)  # no change: keep the date
        assert db.get_issue(conn, 1)["stage_changed_at"] == first
        db.save_progress(conn, 1, "pr_open", "https://github.com/o/p/pull/2")
        issue = db.get_issue(conn, 1)
        assert issue["stage"] == "pr_open" and issue["pr_url"].endswith("/2")


def test_old_databases_get_new_columns_without_losing_issues():
    db.DB_PATH.parent.mkdir(exist_ok=True)
    old = sqlite3.connect(db.DB_PATH)
    old.execute(
        "CREATE TABLE issues (id INTEGER PRIMARY KEY, repo TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, "
        "stars INTEGER NOT NULL, language TEXT NOT NULL, created_at TEXT NOT NULL, found_at TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'new')"
    )
    old.execute("INSERT INTO issues VALUES (1, 'o/p', 'Old', 'https://github.com/o/p/issues/1', 5, 'python', 'x', 'x', 'new')")
    old.commit()
    old.close()
    with db.connect() as conn:
        issue = db.get_issue(conn, 1)
        assert issue["title"] == "Old" and issue["summary"] is None and issue["stage"] is None


def test_star_cache_expires():
    with db.connect() as conn:
        db.save_repo_stars(conn, {"o/p": 7})
        assert db.load_repo_stars(conn, timedelta(days=1)) == {"o/p": 7}
        conn.execute("UPDATE repo_stars SET checked_at = ?", ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),))
        assert db.load_repo_stars(conn, timedelta(days=1)) == {}
