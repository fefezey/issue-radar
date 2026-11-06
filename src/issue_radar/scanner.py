import threading
import time
from datetime import datetime, timedelta, timezone

from issue_radar import ai, db, settings
import httpx

from issue_radar.github import check_issues, contributed_repos, find_issues, has_token, repo_info, track_issues
from issue_radar.i18n import DEFAULT_LANGUAGE, translate
from issue_radar.notify import notify, notify_new_issues

SCAN_INTERVAL = 10 * 60  # seconds between scans
RETRY_INTERVAL = 5 * 60  # after a failed scan (e.g. GitHub rate limit), try again sooner
NOTIFY_INTERVAL = 60 * 60  # at most one notification per hour
STARS_MAX_AGE = timedelta(days=1)  # look up a repository's star count again after this
SEARCH_PAUSE = 5  # seconds between two languages' searches; GitHub's search is sensitive to bursts
MIN_SCAN_GAP = 60  # even when woken early (settings saved), wait this long after the last scan
CONTRIBUTIONS_MAX_AGE = timedelta(days=1)  # look up your own pull requests again after this

RECHECK_BATCH = 20  # saved issues checked again on GitHub after each scan, in one request
TRACK_BATCH = 30  # interested issues followed per scan, in one request
REPO_INFO_BATCH = 8  # projects whose description and newcomer signal are looked up per scan
REPO_INFO_MAX_AGE = timedelta(days=1)

# Read by the web page to show what the scanner is doing.
status = {
    "scanning": False,
    "last_scan": None,
    "error": None,  # what went wrong in the last scan, or None
    "error_kind": None,  # "no_token" | "rate_limit" | "other"
    "retry_at": None,  # when the next try starts, after a failed scan
    "has_token": True,  # are we signed in to GitHub?
}


def _error_kind(error: Exception) -> str:
    if not status["has_token"]:
        return "no_token"
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (403, 429):
        return "rate_limit"
    return "other"


def recheck() -> None:
    """Check saved issues again, so ones that were closed or taken since
    we found them drop out of the list. Needs a GitHub login."""
    if not status["has_token"]:
        return
    with db.connect() as conn:
        issues = db.issues_to_recheck(conn, RECHECK_BATCH)
    if not issues:
        return
    try:
        results, labels = check_issues({issue["id"]: issue["url"] for issue in issues})
    except (httpx.HTTPError, ValueError) as error:
        print(f"Couldn't re-check issues: {error}", flush=True)
        return
    with db.connect() as conn:
        db.set_availability(conn, results, labels)
        lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
    # An issue you wanted has just been taken by someone else: tell you now.
    for issue in issues:
        if issue["status"] == "interested" and results.get(issue["id"]) == "taken":
            notify("Issue Radar", translate(lang, "notify.taken"), issue["title"])


def track() -> None:
    """Follow the issues you're interested in: commented, assigned, pull
    request opened, merged. Tells you when you're assigned or merged."""
    if not status["has_token"]:
        return
    with db.connect() as conn:
        issues = db.issues_to_track(conn, TRACK_BATCH)
        lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
    if not issues:
        return
    try:
        progress = track_issues({issue["id"]: issue["url"] for issue in issues})
    except (httpx.HTTPError, ValueError, KeyError) as error:
        print(f"Couldn't follow your progress: {error}", flush=True)
        return

    reached = []
    with db.connect() as conn:
        for issue in issues:
            now = progress.get(issue["id"])
            if now is None:
                continue
            if now["stage"] != issue["stage"] and now["stage"] in ("assigned", "merged"):
                reached.append((issue, now["stage"]))
            db.save_progress(conn, issue["id"], now["stage"], now["pr_url"])
    for issue, stage in reached:
        notify("Issue Radar", translate(lang, f"notify.{stage}"), issue["title"])


def refresh_repo_info() -> None:
    """Look up what projects on the list are and whether they merge outsiders'
    pull requests. A few per scan, each at most once a day."""
    with db.connect() as conn:
        repos = db.repos_needing_info(conn, REPO_INFO_MAX_AGE, REPO_INFO_BATCH)
    for repo in repos:
        try:
            info = repo_info(repo)
        except httpx.HTTPError as error:
            print(f"Couldn't get project info ({repo}): {error}", flush=True)
            continue
        with db.connect() as conn:
            db.save_repo_info(conn, repo, info)

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
        print(f"Couldn't get your contributions: {error}", flush=True)
        return
    with db.connect() as conn:
        db.save_contributions(conn, counts)
    time.sleep(SEARCH_PAUSE)  # don't search again right away


def pick_languages_on_first_run() -> None:
    """If you've never picked languages, start with the ones you use on GitHub.
    Once you've saved your own choice, we leave it alone."""
    global _looked_at_github_languages
    if _looked_at_github_languages:
        return
    with db.connect() as conn:
        if settings.languages_were_chosen(conn):
            return
    languages = settings.languages_from_github()
    if languages:
        print(f"Picked your languages from GitHub: {', '.join(languages)}", flush=True)
    # Signed in but nothing we can search (say, only HTML): keep the defaults, don't ask every scan.
    _looked_at_github_languages = has_token()


_looked_at_github_languages = False


def scan_forever() -> None:
    """Scan every SCAN_INTERVAL seconds and notify about new issues.

    Issues found between notifications are collected and sent together,
    so you get at most one notification per NOTIFY_INTERVAL.
    """
    pending: list[dict] = []
    last_notified: float | None = None

    while True:
        status["scanning"] = True
        status["has_token"] = has_token()
        try:
            refresh_contributions()
            pick_languages_on_first_run()
            new_issues, error = scan()
            pending += new_issues
            if new_issues:
                ai.wake.set()  # summarize them now
            if not error:
                time.sleep(SEARCH_PAUSE)
                recheck()
                track()
                refresh_repo_info()
        except Exception as e:  # keep scanning even if one scan fails
            error = e
        finally:
            status["scanning"] = False
            status["last_scan"] = datetime.now(timezone.utc)
        status["error"] = str(error) if error else None
        status["error_kind"] = _error_kind(error) if error else None
        status["retry_at"] = status["last_scan"] + timedelta(seconds=RETRY_INTERVAL) if error else None
        if error:
            print(f"Scan failed: {error}", flush=True)

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
