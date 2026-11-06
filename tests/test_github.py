"""What we make of GitHub's answers. No network: answers are made up here."""

from datetime import datetime, timedelta, timezone

import httpx

from issue_radar import github

ME = "newcomer"


def fake_answers(monkeypatch, **issues):
    monkeypatch.setattr(github, "_ask_about_issues", lambda urls, fragment: (ME, issues))


def check_fields(state="OPEN", assignees=(), pr_authors=(), comments=()):
    return {
        "state": state,
        "labels": {"nodes": [{"name": "good first issue"}]},
        "assignees": {"nodes": [{"login": login} for login in assignees]},
        "closedByPullRequestsReferences": {"nodes": [{"author": {"login": login}} for login in pr_authors]},
        "comments": {"nodes": [{"author": {"login": login}, "body": body} for login, body in comments]},
    }


def test_check_issues(monkeypatch):
    fake_answers(
        monkeypatch,
        **{
            "1": check_fields(),
            "2": check_fields(state="CLOSED"),
            "3": check_fields(assignees=["someone"]),
            "4": check_fields(assignees=[ME]),  # you: still yours to work on
            "5": check_fields(pr_authors=["someone"]),
            "6": check_fields(comments=[("someone", "Can I work on this?")]),
            "7": check_fields(comments=[(ME, "I'd like to work on this")]),
            "8": None,  # deleted or moved
        },
    )
    results, labels = github.check_issues({})
    assert results == {
        "1": "open", "2": "closed", "3": "taken", "4": "open",
        "5": "taken", "6": "taken", "7": "open", "8": "closed",
    }
    assert labels["1"] == ["good first issue"]


def track_fields(assignees=(), commenters=(), linked=(), mentioned=()):
    pr = lambda number, state, author: {"number": number, "url": f"https://github.com/o/p/pull/{number}", "state": state, "author": {"login": author}}
    return {
        "assignees": {"nodes": [{"login": login} for login in assignees]},
        "comments": {"nodes": [{"author": {"login": login}} for login in commenters]},
        "closedByPullRequestsReferences": {"nodes": [pr(*p) for p in linked]},
        "timelineItems": {"nodes": [{"source": pr(*p)} for p in mentioned] + [{"source": {}}]},
    }


def test_track_issues(monkeypatch):
    fake_answers(
        monkeypatch,
        **{
            "1": track_fields(),
            "2": track_fields(commenters=[ME]),
            "3": track_fields(commenters=[ME], assignees=[ME]),
            "4": track_fields(assignees=[ME], mentioned=[(7, "OPEN", ME)]),
            "5": track_fields(linked=[(8, "MERGED", ME), (9, "OPEN", ME)]),
            "6": track_fields(linked=[(10, "OPEN", "someone")]),  # not your pull request
        },
    )
    progress = github.track_issues({})
    assert {key: value["stage"] for key, value in progress.items()} == {
        "1": None, "2": "commented", "3": "assigned", "4": "pr_open", "5": "merged", "6": None,
    }
    assert progress["5"]["pr_url"].endswith("/pull/8")


def test_repo_info_counts_outsiders_merged_pull_requests(monkeypatch):
    now = datetime.now(timezone.utc)
    pull = lambda days_ago, role, kind="User", merged=True: {
        "merged_at": (now - timedelta(days=days_ago)).isoformat() if merged else None,
        "author_association": role,
        "user": {"type": kind},
    }

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls"):
            return httpx.Response(200, json=[
                pull(3, "CONTRIBUTOR"),
                pull(10, "FIRST_TIME_CONTRIBUTOR"),
                pull(5, "MEMBER"),  # the team itself
                pull(1, "NONE", kind="Bot"),  # a bot
                pull(2, "CONTRIBUTOR", merged=False),  # closed without merging
                pull(200, "CONTRIBUTOR"),  # too long ago
            ])
        return httpx.Response(200, json={"description": " A project. ", "stargazers_count": 42})

    monkeypatch.setattr(
        github, "_client", lambda: httpx.Client(base_url=github.API_URL, transport=httpx.MockTransport(answer))
    )
    assert github.repo_info("o/p") == {"description": "A project.", "stars": 42, "outside_merged": 2}
