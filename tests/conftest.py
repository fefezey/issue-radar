import pytest

from issue_radar import db


@pytest.fixture(autouse=True)
def fresh_database(tmp_path, monkeypatch):
    """Every test gets its own empty database, never your real one."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "issues.db")


def make_issue(issue_id: int, repo: str = "owner/project", **extra) -> dict:
    """An issue as GitHub's search returns it, after find_issues adds stars and repo."""
    issue = {
        "id": issue_id,
        "repo": repo,
        "title": f"Issue {issue_id}",
        "html_url": f"https://github.com/{repo}/issues/{issue_id}",
        "stars": 500,
        "created_at": "2026-11-01T10:00:00+00:00",
        "body": "A description that is long enough to be worth summarizing. " * 5,
        "labels": [{"name": "good first issue"}],
    }
    issue.update(extra)
    return issue
