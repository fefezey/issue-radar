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


def _is_claimed(client: httpx.Client, issue: dict) -> bool:
    """True if someone has said in the comments that they are taking the issue."""
    if issue["comments"] == 0:
        return False
    response = client.get(issue["comments_url"].removeprefix(API_URL))
    response.raise_for_status()
    return any(
        phrase in comment["body"].lower()
        for comment in response.json()
        for phrase in CLAIM_PHRASES
    )


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
    query = (
        f'label:"good first issue" state:open is:issue language:{language} '
        "no:assignee -linked:pr"
    )

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
