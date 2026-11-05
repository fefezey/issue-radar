import time
from datetime import datetime, timezone

from issue_radar import db
from issue_radar.github import find_issues
from issue_radar.i18n import DEFAULT_LANGUAGE
from issue_radar.languages import LANGUAGES
from issue_radar.notify import notify_new_issues

SCAN_INTERVAL = 10 * 60  # seconds between scans
NOTIFY_INTERVAL = 60 * 60  # at most one notification per hour

# Read by the web page to show what the scanner is doing.
status = {"scanning": False, "last_scan": None, "error": None}


def scan() -> list[dict]:
    """Look for new issues on GitHub, save them and return the ones we hadn't seen."""
    # Fetch everything first: talking to GitHub takes a while, and we must not
    # keep the database locked meanwhile, or the web page can't save anything.
    found = {language: find_issues(language, limit=20) for language in LANGUAGES}

    new_issues = []
    with db.connect() as conn:
        for language, issues in found.items():
            for issue in issues:
                issue["language"] = language
            new_issues += db.save_issues(conn, issues, language)
    return new_issues


def scan_forever() -> None:
    """Scan every SCAN_INTERVAL seconds and notify about new issues.

    Issues found between notifications are collected and sent together,
    so you get at most one notification per NOTIFY_INTERVAL.
    """
    pending: list[dict] = []
    last_notified: float | None = None

    while True:
        status["scanning"] = True
        try:
            pending += scan()
            status["error"] = None
        except Exception as error:  # keep scanning even if one scan fails
            status["error"] = str(error)
            print(f"Tarama başarısız: {error}")
        finally:
            status["scanning"] = False
            status["last_scan"] = datetime.now(timezone.utc)

        can_notify = last_notified is None or time.monotonic() - last_notified >= NOTIFY_INTERVAL
        if pending and can_notify:
            with db.connect() as conn:
                lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
            notify_new_issues(pending, lang)
            pending = []
            last_notified = time.monotonic()

        time.sleep(SCAN_INTERVAL)
