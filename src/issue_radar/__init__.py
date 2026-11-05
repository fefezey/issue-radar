from issue_radar.github import find_issues


def main() -> None:
    for issue in find_issues("javascript"):
        print(f"[{issue['repo']}] ⭐ {issue['stars']}  {issue['title']}")
        print(f"    {issue['html_url']}")
