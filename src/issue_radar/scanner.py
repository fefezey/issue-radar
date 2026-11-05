import threading
import time
from datetime import datetime, timedelta, timezone

from issue_radar import ai, db, settings
from issue_radar.github import contributed_repos, find_issues
from issue_radar.i18n import DEFAULT_LANGUAGE
from issue_radar.notify import notify_new_issues

SCAN_INTERVAL = 10 * 60  # seconds between scans
RETRY_INTERVAL = 5 * 60  # after a failed scan (e.g. GitHub rate limit), try again sooner
NOTIFY_INTERVAL = 60 * 60  # at most one notification per hour
STARS_MAX_AGE = timedelta(days=1)  # look up a repository's star count again after this
SEARCH_PAUSE = 5  # seconds between two languages' searches; GitHub's search is sensitive to bursts
MIN_SCAN_GAP = 60  # even when woken early (settings saved), wait this long after the last scan
CONTRIBUTIONS_MAX_AGE = timedelta(days=1)  # look up your own pull requests again after this

# Read by the web page to show what the scanner is doing.
status = {"scanning": False, "last_scan": None, "error": None}

# Set this to start the next scan right away instead of waiting.
wake = threading.Event()


def scan() -> tuple[list[dict], Exception | None]:
    """Look for new issues on GitHub and save them.

    Returns the issues we hadn't seen before, and the error that stopped the
    scan early, if any. Whatever was found before the error is still saved,
    so the next try has less work to do.
    """
    with db.connect() as conn:
        languages = settings.search_languages(conn)
        min_stars = settings.min_stars(conn)
        cached_stars = db.load_repo_stars(conn, max_age=STARS_MAX_AGE)

    # Fetch everything first: talking to GitHub takes a while, and we must not
    # keep the database locked meanwhile, or the web page can't save anything.
    stars = dict(cached_stars)
    found: dict[str, list[dict]] = {}
    error = None
    for i, language in enumerate(languages):
        if i > 0:
            time.sleep(SEARCH_PAUSE)
        try:
            found[language] = find_issues(language, min_stars=min_stars, limit=20, stars=stars)
        except Exception as e:  # e.g. GitHub's rate limit; keep what we have
            error = e
            break

    new_issues = []
    with db.connect() as conn:
        for language, issues in found.items():
            for issue in issues:
                issue["language"] = language
            new_issues += db.save_issues(conn, issues, language)
        db.save_repo_stars(conn, {repo: n for repo, n in stars.items() if repo not in cached_stars})
    return new_issues, error


def refresh_contributions() -> None:
    """Once a day, look up which projects you've already sent pull requests to.

    Failing here is not a problem: issues are still shown, just without the
    "your first contribution" badge.
    """
    with db.connect() as conn:
        checked = db.contributions_checked_at(conn)
    if checked and datetime.now(timezone.utc) - checked < CONTRIBUTIONS_MAX_AGE:
        return
    try:
        counts = contributed_repos()
    except Exception as error:
        print(f"Katkıların alınamadı: {error}", flush=True)
        return
    with db.connect() as conn:
        db.save_contributions(conn, counts)
    time.sleep(SEARCH_PAUSE)  # don't search again right away


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
            refresh_contributions()
            new_issues, error = scan()
            pending += new_issues
            if new_issues:
                ai.wake.set()  # summarize them now
        except Exception as e:  # keep scanning even if one scan fails
            error = e
        finally:
            status["scanning"] = False
            status["last_scan"] = datetime.now(timezone.utc)
        status["error"] = str(error) if error else None
        if error:
            print(f"Tarama başarısız: {error}", flush=True)

        can_notify = last_notified is None or time.monotonic() - last_notified >= NOTIFY_INTERVAL
        if pending and can_notify:
            with db.connect() as conn:
                lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
            notify_new_issues(pending, lang)
            pending = []
            last_notified = time.monotonic()

        finished = time.monotonic()
        wake.wait(RETRY_INTERVAL if status["error"] else SCAN_INTERVAL)
        wake.clear()
        # Scanning again right after a scan trips GitHub's rate limit.
        time.sleep(max(0, MIN_SCAN_GAP - (time.monotonic() - finished)))
