import json
from datetime import datetime, timedelta, timezone
import os
import shutil
import subprocess

import httpx

API_URL = "https://api.github.com"


def _token() -> str | None:
    """Use GITHUB_TOKEN if set, otherwise the GitHub CLI's login (if any)."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip() or None
    return None


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API_URL, headers=headers, timeout=10)


# Labels projects use for issues meant for newcomers.
BEGINNER_LABELS = (
    "good first issue",
    "good-first-issue",
    "first-timers-only",
    "beginner",
    "beginner-friendly",
)

# Phrases people use in comments when they take an issue.
CLAIM_PHRASES = (
    "i'd like to work",
    "i would like to work",
    "i want to work",
    "can i work",
    "could i work",
    "may i work",
    "i'll work on",
    "i will work on",
    "i'm working on",
    "i am working on",
    "assign me",
    "assign this to me",
    "can i take",
    "i'll take",
    "i will take",
    "i'd like to take",
)


def has_token() -> bool:
    return _token() is not None


def _mentions_claim(text: str) -> bool:
    text = text.lower()
    return any(phrase in text for phrase in CLAIM_PHRASES)


def _is_claimed(client: httpx.Client, issue: dict) -> bool:
    """True if someone has said in the comments that they are taking the issue."""
    if issue["comments"] == 0:
        return False
    response = client.get(issue["comments_url"].removeprefix(API_URL), params={"per_page": 100})
    response.raise_for_status()
    return any(_mentions_claim(comment["body"] or "") for comment in response.json())


def find_issues(
    language: str,
    min_stars: int = 100,
    limit: int = 10,
    stars: dict[str, int] | None = None,
) -> list[dict]:
    """Return the newest open "good first issue"s in the given language that
    nobody has taken yet, only from repositories with at least `min_stars` stars.

    `stars` holds star counts we already know; new lookups are added to it,
    so the caller can keep them for the next scan.
    """
    if stars is None:
        stars = {}
    # no:assignee  -> nobody is assigned to it
    # -linked:pr   -> no pull request has been opened for it
    labels = ",".join(f'"{label}"' for label in BEGINNER_LABELS)  # comma = any of them
    query = f"label:{labels} state:open is:issue language:{language} no:assignee -linked:pr"

    with _client() as client:
        response = client.get(
            "/search/issues",
            params={"q": query, "sort": "created", "order": "desc", "per_page": 100},
        )
        response.raise_for_status()

        # GitHub's issue search can't filter by stars, so we look up each
        # repository we don't know yet and remember its star count.
        issues = []
        for issue in response.json()["items"]:
            repo = issue["repository_url"].removeprefix(f"{API_URL}/repos/")
            if repo not in stars:
                repo_info = client.get(f"/repos/{repo}")
                repo_info.raise_for_status()
                stars[repo] = repo_info.json()["stargazers_count"]

            if stars[repo] >= min_stars and not _is_claimed(client, issue):
                issue["repo"] = repo
                issue["stars"] = stars[repo]
                issues.append(issue)
                if len(issues) == limit:
                    break

    return issues


def contributed_repos(max_pages: int = 3) -> dict[str, int]:
    """Repositories where the signed-in user has opened pull requests, and how many.

    Every PR counts, merged or not: once you've opened one somewhere,
    it's no longer your first contribution there.
    """
    counts: dict[str, int] = {}
    with _client() as client:
        user = client.get("/user")
        user.raise_for_status()
        login = user.json()["login"]

        for page in range(1, max_pages + 1):
            response = client.get(
                "/search/issues",
                params={"q": f"is:pr author:{login}", "per_page": 100, "page": page},
            )
            response.raise_for_status()
            pull_requests = response.json()["items"]
            for pr in pull_requests:
                repo = pr["repository_url"].removeprefix(f"{API_URL}/repos/")
                counts[repo] = counts.get(repo, 0) + 1
            if len(pull_requests) < 100:
                break
    return counts


def issue_body(url: str) -> str:
    """The description of an issue, from its web address
    ("https://github.com/owner/repo/issues/12")."""
    path = url.removeprefix("https://github.com/")
    with _client() as client:
        response = client.get(f"/repos/{path}")
        response.raise_for_status()
        return response.json().get("body") or ""


# What we ask GitHub about each issue we already have, to see if it's still free.
_CHECK_FIELDS = """
fragment Check on Issue {
  state
  labels(first: 20) { nodes { name } }
  assignees(first: 10) { nodes { login } }
  closedByPullRequestsReferences(first: 10, includeClosedPrs: false) { nodes { author { login } } }
  comments(last: 50) { nodes { author { login } body } }
}
"""


def check_issues(urls: dict[int, str]) -> tuple[dict[int, str], dict[int, list[str]]]:
    """Look again at issues we saved earlier, all in one request.

    Returns, by issue id, "open", "taken" or "closed", and the issue's
    current labels. Your own assignment, pull request or comment doesn't
    count as "taken". Issues GitHub couldn't answer about are left out.
    """
    aliases: dict[str, int] = {}
    parts = []
    for i, (issue_id, url) in enumerate(urls.items()):
        owner, name, _, number = url.removeprefix("https://github.com/").split("/")[:4]
        aliases[f"i{i}"] = issue_id
        parts.append(
            f"i{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
            f"{{ issue(number: {int(number)}) {{ ...Check }} }}"
        )
    query = "query { viewer { login } " + " ".join(parts) + " }" + _CHECK_FIELDS

    with _client() as client:
        response = client.post("/graphql", json={"query": query})
        response.raise_for_status()
    data = response.json().get("data") or {}
    me = (data.get("viewer") or {}).get("login", "")

    def someone_else(actor: dict | None) -> bool:
        return (actor or {}).get("login") not in (me, None)

    results: dict[int, str] = {}
    labels: dict[int, list[str]] = {}
    for alias, issue_id in aliases.items():
        repo = data.get(alias)
        if repo is None:  # GitHub didn't answer for this one; try again next time
            continue
        issue = repo.get("issue")
        if issue is not None:
            labels[issue_id] = [label["name"] for label in issue["labels"]["nodes"]]
        if issue is None or issue["state"] == "CLOSED":  # closed, deleted or moved
            results[issue_id] = "closed"
        elif (
            any(someone_else(a) for a in issue["assignees"]["nodes"])
            or any(someone_else(pr["author"]) for pr in issue["closedByPullRequestsReferences"]["nodes"])
            or any(
                someone_else(c["author"]) and _mentions_claim(c["body"] or "")
                for c in issue["comments"]["nodes"]
            )
        ):
            results[issue_id] = "taken"
        else:
            results[issue_id] = "open"
    return results, labels


# How far back to look at a project's merged pull requests.
NEWCOMER_WINDOW = timedelta(days=90)

# Author roles GitHub gives people outside the project's own team.
# (There are "first-timer" roles too, but GitHub turns them into
# "CONTRIBUTOR" once the pull request is merged, so we can't count them.)
_OUTSIDE_ROLES = {"CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"}


def repo_info(repo: str) -> dict:
    """What a project is, and whether it takes pull requests from outsiders.

    Counts pull requests merged in the last NEWCOMER_WINDOW that came from
    outside the project's team. Bots don't count. Two requests to GitHub's regular API (not the search).
    """
    since = datetime.now(timezone.utc) - NEWCOMER_WINDOW
    with _client() as client:
        about = client.get(f"/repos/{repo}")
        about.raise_for_status()
        pulls = client.get(
            f"/repos/{repo}/pulls",
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100},
        )
        pulls.raise_for_status()

    outside = 0
    for pr in pulls.json():
        merged = pr.get("merged_at")
        user = pr.get("user") or {}
        if not merged or datetime.fromisoformat(merged) < since or user.get("type") == "Bot":
            continue
        if pr.get("author_association") in _OUTSIDE_ROLES:
            outside += 1

    info = about.json()
    return {
        "description": (info.get("description") or "").strip(),
        "stars": info["stargazers_count"],
        "outside_merged": outside,
    }


def contributing_guide(repo: str) -> str:
    """The text of the project's contributing guide, or "" if it has none."""
    with _client() as client:
        profile = client.get(f"/repos/{repo}/community/profile")
        if profile.status_code == 404:  # forks and some repositories have no profile
            return ""
        profile.raise_for_status()
        guide = (profile.json().get("files") or {}).get("contributing")
        if not guide or not guide.get("url"):
            return ""
        text = client.get(guide["url"], headers={"Accept": "application/vnd.github.raw"})
        text.raise_for_status()
        return text.text
