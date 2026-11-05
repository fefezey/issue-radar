from datetime import datetime, timezone

from flask import Flask, abort, g, redirect, render_template, request, url_for

from issue_radar import ai, db, settings
from issue_radar.i18n import DEFAULT_LANGUAGE, available_languages, translate
from issue_radar.languages import SUPPORTED_LANGUAGES, language_name
from issue_radar.scanner import status, wake

app = Flask(__name__)
app.add_template_filter(language_name, "language")

TABS = ("new", "interested", "hidden", "settings")


def t(key: str, count: int | None = None, **values) -> str:
    """Translate into the language of the current page."""
    return translate(g.lang, key, count, **values)


@app.before_request
def pick_language():
    """Use the saved language; on the first visit, save the browser's language.

    Saving it also tells the scanner which language to use for notifications.
    """
    with db.connect() as conn:
        lang = db.get_setting(conn, "language")
        if lang not in available_languages():
            lang = request.accept_languages.best_match(available_languages()) or DEFAULT_LANGUAGE
            db.set_setting(conn, "language", lang)
    g.lang = lang


@app.context_processor
def template_helpers():
    return {"t": t, "lang": g.lang, "languages": available_languages()}


@app.template_filter("ago")
def ago(timestamp: str) -> str:
    """'2026-11-05T12:00:00Z' -> '3 hours ago'"""
    seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
    if seconds < 3600:
        return t("time.minutes", max(1, int(seconds // 60)))
    if seconds < 86400:
        return t("time.hours", int(seconds // 3600))
    return t("time.days", int(seconds // 86400))


@app.template_filter("stars")
def stars(count: int) -> str:
    """1234 -> '1.2k stars'"""
    short = f"{count / 1000:.1f}k" if count >= 1000 else str(count)
    return t("issue.stars", count, stars=short)


def scan_text() -> str:
    if status["scanning"]:
        return t("scan.first") if status["last_scan"] is None else t("scan.running")
    if status["error"]:
        return t("scan.failed")
    if status["last_scan"] is None:
        return t("scan.waiting")
    minutes = int((datetime.now(timezone.utc) - status["last_scan"]).total_seconds() // 60)
    return t("scan.just_now") if minutes == 0 else t("scan.minutes", minutes)


@app.get("/")
def index():
    tab = request.args.get("tab", "new")
    if tab not in TABS:
        tab = "new"
    with db.connect() as conn:
        languages = settings.search_languages(conn)
        min_stars = settings.min_stars(conn)
        new_issues = db.list_issues(conn, "new", languages, min_stars)
        interested_issues = db.list_issues(conn, "interested")
        contributed = db.load_contributions(conn) or {}
        if contributed:
            # Projects you haven't contributed to yet come first; newest first within each group.
            new_issues = sorted(new_issues, key=lambda issue: issue["repo"] in contributed)
        hidden_repos = db.list_blocked_repos(conn)
        undo_issue = request.args.get("undo_issue", type=int)
        skipped = db.get_issue(conn, undo_issue) if undo_issue else None

    return render_template(
        "index.html",
        tab=tab,
        issues=new_issues if tab == "new" else interested_issues,
        counts={"new": len(new_issues), "interested": len(interested_issues), "hidden": len(hidden_repos)},
        hidden_repos=hidden_repos,
        skipped=skipped,
        hidden_repo=request.args.get("undo_repo"),
        contributed=contributed,
        ai_on=ai.status["available"],
        scan_text=scan_text(),
        scanning=status["scanning"],
        scan_failed=bool(status["error"]),
        all_languages=SUPPORTED_LANGUAGES,
        chosen_languages=languages,
        min_stars=min_stars,
        min_stars_choices=settings.MIN_STARS_CHOICES,
        saved=request.args.get("saved") == "1",
        settings_error=request.args.get("error") == "no_language",
    )


@app.post("/settings")
def save_settings():
    stars = request.form.get("min_stars", type=int)
    if stars not in settings.MIN_STARS_CHOICES:
        stars = settings.DEFAULT_MIN_STARS
    try:
        with db.connect() as conn:
            settings.save(conn, request.form.getlist("languages"), stars)
    except ValueError:
        return redirect(url_for("index", tab="settings", error="no_language"))
    wake.set()  # scan again right away with the new settings
    return redirect(url_for("index", tab="settings", saved="1"))


@app.post("/language")
def set_language():
    lang = request.form.get("language")
    if lang in available_languages():
        with db.connect() as conn:
            db.set_setting(conn, "language", lang)
        ai.wake.set()  # write summaries in the new language
    tab = request.form.get("tab", "new")
    return redirect(url_for("index", tab=tab if tab in TABS else "new"))


@app.post("/issues/<int:issue_id>/interested")
def interested(issue_id: int):
    with db.connect() as conn:
        issue = db.get_issue(conn, issue_id)
        if issue is None:
            abort(404)
        db.set_status(conn, issue_id, "interested")
    return redirect(issue["url"])


@app.post("/issues/<int:issue_id>/skip")
def skip(issue_id: int):
    with db.connect() as conn:
        db.set_status(conn, issue_id, "skipped")
    return redirect(url_for("index", undo_issue=issue_id))


@app.post("/issues/<int:issue_id>/restore")
def restore(issue_id: int):
    """Put an issue back in the "new" list (undo a skip, or give up on an issue)."""
    with db.connect() as conn:
        db.set_status(conn, issue_id, "new")
    return redirect(url_for("index", tab=request.form.get("tab", "new")))


@app.post("/repos/block")
def block():
    repo = request.form["repo"]
    with db.connect() as conn:
        db.block_repo(conn, repo)
    return redirect(url_for("index", undo_repo=repo))


@app.post("/repos/unblock")
def unblock():
    with db.connect() as conn:
        db.unblock_repo(conn, request.form["repo"])
    return redirect(url_for("index", tab=request.form.get("tab", "new")))
