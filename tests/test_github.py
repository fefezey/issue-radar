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
            "9": check_fields(state="CLOSED", pr_authors=[ME]),  # your pull request closed it
            "10": check_fields(comments=[(ME, "Is this still reproducible?")]),  # any comment of yours
        },
    )
    results, labels, yours = github.check_issues({})
    assert results == {
        "1": "open", "2": "closed", "3": "taken", "4": "open",
        "5": "taken", "6": "taken", "7": "open", "8": "closed", "9": "closed", "10": "open",
    }
    assert labels["1"] == ["good first issue"]
    assert yours == {"4", "7", "9", "10"}


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
        if request.url.path == "/graphql":
            return httpx.Response(200, json={"data": {"repository": {"pullRequests": {"nodes": []}}}})
        return httpx.Response(200, json={"description": " A project. ", "stargazers_count": 42})

    monkeypatch.setattr(
        github, "_client", lambda: httpx.Client(base_url=github.API_URL, transport=httpx.MockTransport(answer))
    )
    assert github.repo_info("o/p") == {
        "description": "A project.",
        "stars": 42,
        "outside_merged": 2,
        "response_hours": None,  # no pull requests to tell from
    }


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def pr(days_ago, answered_after_hours=None, role="CONTRIBUTOR", by="MEMBER", kind="User", merged_after_hours=None):
    created = NOW - timedelta(days=days_ago)
    at = lambda hours: (created + timedelta(hours=hours)).isoformat()
    comments = [{"createdAt": at(0.1), "authorAssociation": "NONE", "author": {"__typename": "Bot"}}]  # a CLA bot
    if answered_after_hours is not None:
        comments.append({"createdAt": at(answered_after_hours), "authorAssociation": by, "author": {"__typename": "User"}})
    return {
        "createdAt": created.isoformat(),
        "mergedAt": at(merged_after_hours) if merged_after_hours is not None else None,
        "authorAssociation": role,
        "author": {"__typename": kind},
        "comments": {"nodes": comments},
        "reviews": {"nodes": []},
    }


def test_response_hours_is_the_usual_wait_for_the_teams_first_answer():
    pulls = [
        pr(20, answered_after_hours=2),
        pr(30, answered_after_hours=10),
        pr(40, merged_after_hours=30),  # merging counts as an answer
        pr(50, answered_after_hours=1, by="CONTRIBUTOR"),  # another outsider: not an answer...
        pr(10, role="MEMBER", answered_after_hours=500),  # the team's own pull request
        pr(5, kind="Bot", answered_after_hours=500),  # a bot's
        pr(200, answered_after_hours=500),  # too long ago
        pr(2),  # too new to say it went unanswered
    ]
    # Waits: 2, 10, 30 and never (the one only another outsider answered) -> 10.
    assert github.response_hours(pulls, NOW) == 10


def test_response_hours_when_most_go_unanswered_or_there_are_too_few():
    assert github.response_hours([pr(20), pr(30), pr(40, answered_after_hours=5)], NOW) == -1
    assert github.response_hours([pr(20, answered_after_hours=5), pr(30)], NOW) is None


def test_guess_languages_from_your_repos(monkeypatch):
    own = [
        {"full_name": "me/a", "language": "C", "fork": False},
        {"full_name": "me/b", "language": "C", "fork": False},
        {"full_name": "me/site", "language": "HTML", "fork": False},  # not a language we search
        {"full_name": "me/fork", "language": "Rust", "fork": True},  # someone else's code
        {"full_name": "me/c", "language": "Python", "fork": False},
    ]
    languages = {"x/ts": "TypeScript", "y/cpp": "C++"}

    def answer(request):
        if request.url.path == "/users/me/repos":
            return httpx.Response(200, json=own)
        name = request.url.path.removeprefix("/repos/")
        if name not in languages:
            return httpx.Response(404)
        return httpx.Response(200, json={"language": languages[name]})

    monkeypatch.setattr(
        github, "_client", lambda: httpx.Client(base_url=github.API_URL, transport=httpx.MockTransport(answer))
    )
    # Contributions count double; your own repos once; gone repos are skipped.
    assert github.guess_languages("me", ["x/ts", "gone/repo", "y/cpp", "me/a"]) == ["c", "typescript", "cpp", "python"]


def test_my_pull_requests_counts_projects_and_keeps_merged_ones_elsewhere(monkeypatch):
    def item(repo, number, merged_at=None):
        return {
            "repository_url": f"{github.API_URL}/repos/{repo}",
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "title": f"PR {number}",
            "pull_request": {"merged_at": merged_at},
        }

    def answer(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "Me"})
        return httpx.Response(200, json={"items": [
            item("o/p", 1, "2026-11-01T10:00:00Z"),
            item("o/p", 2),  # still open, or closed without merging
            item("x/y", 3, "2026-11-05T10:00:00Z"),
            item("me/own", 4, "2026-11-06T10:00:00Z"),  # your own project: not a contribution
        ]})

    monkeypatch.setattr(
        github, "_client", lambda: httpx.Client(base_url=github.API_URL, transport=httpx.MockTransport(answer))
    )
    counts, merged = github.my_pull_requests()
    assert counts == {"o/p": 2, "x/y": 1, "me/own": 1}
    assert [pr["url"] for pr in merged] == ["https://github.com/x/y/pull/3", "https://github.com/o/p/pull/1"]
