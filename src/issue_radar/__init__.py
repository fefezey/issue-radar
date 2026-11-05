from issue_radar import db
from issue_radar.github import find_issues

# Languages to search. Change or add to this list to see other languages.
LANGUAGES = ["python", "javascript"]


def scan() -> list[dict]:
    """Look for new issues on GitHub, save them and return the ones we hadn't seen."""
    new_issues = []
    with db.connect() as conn:
        for language in LANGUAGES:
            issues = find_issues(language, limit=20)
            new_issues += db.save_issues(conn, issues, language)
    return new_issues


def main() -> None:
    from issue_radar.web import app

    print("GitHub taranıyor, bu biraz sürebilir...")
    print(f"{len(scan())} yeni iş bulundu.")
    print("Sayfa: http://localhost:8000")
    app.run(port=8000)
