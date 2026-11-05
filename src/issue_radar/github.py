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


def find_issues(language: str, min_stars: int = 100, limit: int = 10) -> list[dict]:
    """Return the newest open "good first issue"s in the given language,
    only from repositories with at least `min_stars` stars."""
    query = f'label:"good first issue" state:open is:issue language:{language}'

    with _client() as client:
        response = client.get(
            "/search/issues",
            params={"q": query, "sort": "created", "order": "desc", "per_page": 100},
        )
        response.raise_for_status()

        # GitHub's issue search can't filter by stars, so we look up each
        # repository once and remember its star count.
        stars: dict[str, int] = {}
        issues = []
        for issue in response.json()["items"]:
            repo = issue["repository_url"].removeprefix(f"{API_URL}/repos/")
            if repo not in stars:
                repo_info = client.get(f"/repos/{repo}")
                repo_info.raise_for_status()
                stars[repo] = repo_info.json()["stargazers_count"]

            if stars[repo] >= min_stars:
                issue["repo"] = repo
                issue["stars"] = stars[repo]
                issues.append(issue)
                if len(issues) == limit:
                    break

    return issues
