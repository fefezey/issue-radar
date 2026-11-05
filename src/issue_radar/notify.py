import subprocess
import sys
from collections import Counter

from issue_radar.languages import language_name


def _quote(text: str) -> str:
    """Make text safe to put inside an AppleScript string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title: str, subtitle: str, message: str) -> None:
    """Show a macOS notification. Does nothing on other systems."""
    if sys.platform != "darwin":
        return
    script = (
        f"display notification {_quote(message)} "
        f"with title {_quote(title)} subtitle {_quote(subtitle)}"
    )
    subprocess.run(["osascript", "-e", script], check=False)


def notify_new_issues(issues: list[dict]) -> None:
    if len(issues) == 1:
        issue = issues[0]
        notify("Issue Radar", issue["repo"], issue["title"])
        return

    by_language = Counter(language_name(issue["language"]) for issue in issues)
    summary = ", ".join(f"{count} {name}" for name, count in by_language.most_common())
    notify("Issue Radar", f"{len(issues)} yeni iş bulundu", summary)
