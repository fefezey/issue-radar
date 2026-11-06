import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from flask import Flask, abort, g, redirect, render_template, request, url_for
from markupsafe import Markup, escape

from issue_radar import ai, db, github, settings
from issue_radar.claiming import DRAFT, PLAN_PLACEHOLDER, policy_from_guide
from issue_radar.github import contributing_guide, file_tree, readme
from issue_radar.guide import find_commands, find_files, name_candidates
from issue_radar.i18n import DEFAULT_LANGUAGE, available_languages, translate
from issue_radar.kinds import kind_of
from issue_radar.languages import SUPPORTED_LANGUAGES, language_name
from issue_radar.notify import notify
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


@app.template_filter("days_since")
def days_since(timestamp: str | None) -> int:
    if not timestamp:
        return 0
    return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).days


@app.template_filter("code")
def code(text: str) -> Markup:
    """Show `backticked` parts of AI summaries as code. Everything else stays plain text."""
    return Markup(re.sub(r"`([^`\n]+)`", r"<code>\1</code>", str(escape(text))))


@app.template_filter("stars")
def stars(count: int) -> str:
    """1234 -> '1.2k stars'"""
    short = f"{count / 1000:.1f}k" if count >= 1000 else str(count)
    return t("issue.stars", count, stars=short)


def _wants_json() -> bool:
    """The page sends its buttons with fetch() and doesn't need a new page back."""
    return request.headers.get("X-Requested-With") == "fetch"


def _done(**redirect_args):
    return ("", 204) if _wants_json() else redirect(url_for("index", **redirect_args))


def scan_text() -> str:
    if status["scanning"]:
        return t("scan.first") if status["last_scan"] is None else t("scan.running")
    if status["error"]:
        return t("scan.failed")
    if status["last_scan"] is None:
        return t("scan.waiting")
    minutes = int((datetime.now(timezone.utc) - status["last_scan"]).total_seconds() // 60)
    return t("scan.just_now") if minutes == 0 else t("scan.minutes", minutes)


def group_by_project(issues: list) -> list[tuple[str, list]]:
    """[(repo, its issues), ...], keeping the order in which projects first appear,
    so one busy project doesn't fill the whole list."""
    groups: dict[str, list] = {}
    for issue in issues:
        groups.setdefault(issue["repo"], []).append(issue)
    return list(groups.items())


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
        new_count = len(new_issues)
        # Docs, tests and translations are the gentlest first contributions.
        kinds = {
            issue["id"]: kind_of(issue["title"], json.loads(issue["labels"] or "[]"))
            for issue in new_issues + interested_issues
        }
        easy_count = sum(1 for issue in new_issues if kinds[issue["id"]])
        easy_only = request.args.get("easy") == "1"
        if easy_only:
            new_issues = [issue for issue in new_issues if kinds[issue["id"]]]
        repos = db.load_repo_info(conn)
        translations = db.load_translations(conn, g.lang)
        undo_issue = request.args.get("undo_issue", type=int)
        skipped = db.get_issue(conn, undo_issue) if undo_issue else None

    return render_template(
        "index.html",
        tab=tab,
        issues=new_issues if tab == "new" else interested_issues,
        counts={"new": new_count, "interested": len(interested_issues), "hidden": len(hidden_repos)},
        groups=group_by_project(new_issues),
        repos=repos,
        translations=translations,
        kinds=kinds,
        easy_count=easy_count,
        easy_only=easy_only,
        hidden_repos=hidden_repos,
        skipped=skipped,
        hidden_repo=request.args.get("undo_repo"),
        contributed=contributed,
        ai_on=ai.status["available"],
        ai_state=ai.status["state"],
        ai_model=ai.MODEL,
        ai_failed=ai.failed_ids(),
        scan_text=scan_text(),
        scanning=status["scanning"],
        scan_failed=bool(status["error"]),
        error_kind=status["error_kind"] or ("no_token" if not status["has_token"] else None),
        retry_at=status["retry_at"].astimezone().strftime("%H:%M") if status["retry_at"] else "",
        all_languages=SUPPORTED_LANGUAGES,
        chosen_languages=languages,
        min_stars=min_stars,
        min_stars_choices=settings.MIN_STARS_CHOICES,
        saved=request.args.get("saved") == "1",
        picked=request.args.get("picked") == "1",
        settings_error=request.args.get("error"),
        github_login=github_login() if tab == "settings" else None,
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


_github_login: dict[str, str] = {}


def github_login() -> str | None:
    """Who we're signed in to GitHub as, asked once (it doesn't change while we run)."""
    if "login" not in _github_login:
        try:
            login = github.whoami()
        except httpx.HTTPError:
            return None  # try again next time
        if not login:
            return None
        _github_login["login"] = login
    return _github_login["login"]


@app.post("/languages/from-github")
def languages_from_github():
    try:
        languages = settings.languages_from_github()
    except httpx.HTTPError:
        languages = None
    if not languages:
        return redirect(url_for("index", tab="settings", error="github_languages"))
    wake.set()
    return redirect(url_for("index", tab="settings", picked="1"))


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
    # The page opens GitHub itself when it uses fetch(); without JavaScript we go there.
    return ("", 204) if _wants_json() else redirect(issue["url"])


GUIDE_MAX_AGE = timedelta(days=7)  # read a project's contributing guide again after this


@app.get("/issues/<int:issue_id>/draft")
def draft(issue_id: int):
    """A comment draft for claiming the issue, and whether the project expects one."""
    with db.connect() as conn:
        issue = db.get_issue(conn, issue_id)
        if issue is None:
            abort(404)
        policy = db.get_claim_policy(conn, issue["repo"], GUIDE_MAX_AGE)
    if policy is None:
        try:
            policy = policy_from_guide(contributing_guide(issue["repo"]))
        except httpx.HTTPError:
            policy = "ask"  # couldn't read the guide; the usual advice, not saved
        else:
            with db.connect() as conn:
                db.save_claim_policy(conn, issue["repo"], policy)
    return {
        "title": issue["title"],
        "url": issue["url"],
        "draft": DRAFT,
        "placeholder": PLAN_PLACEHOLDER,
        "policy": policy,
    }


PROJECT_FILES_MAX_AGE = 24 * 60 * 60  # seconds to keep a project's README, guide and file list
_project_files: dict[str, tuple[float, str, str, list[str]]] = {}


def _project(repo: str) -> tuple[str, str, list[str]]:
    """A project's contributing guide, README and file list, kept for a day."""
    saved = _project_files.get(repo)
    if saved and time.time() - saved[0] < PROJECT_FILES_MAX_AGE:
        return saved[1], saved[2], saved[3]
    guide_text, readme_text, tree = contributing_guide(repo), readme(repo), file_tree(repo)
    _project_files[repo] = (time.time(), guide_text, readme_text, tree)
    return guide_text, readme_text, tree


@app.get("/issues/<int:issue_id>/guide")
def issue_guide(issue_id: int):
    """Where to start: commands to set up and test the project, and files
    named in the issue that exist in the project. Facts, no AI."""
    with db.connect() as conn:
        issue = db.get_issue(conn, issue_id)
    if issue is None:
        abort(404)
    repo = issue["repo"]
    try:
        guide_text, readme_text, tree = _project(repo)
    except httpx.HTTPError:
        return {"error": True}, 502
    paths, identifiers = name_candidates(issue["title"], issue["body"] or "")
    return {
        "title": issue["title"],
        "commands": find_commands(guide_text, readme_text),
        "files": [
            {"path": path, "url": f"https://github.com/{repo}/blob/HEAD/{quote(path)}"}
            for path in find_files(tree, paths, identifiers)
        ],
        "readme_url": f"https://github.com/{repo}#readme",
        "explanation": issue["explanation"] if issue["explanation_lang"] == g.lang else None,
        "ai_on": ai.status["available"],
    }


@app.post("/issues/<int:issue_id>/explain")
def explain_issue(issue_id: int):
    """The guide's plain explanation, made by the local AI model once and kept."""
    with db.connect() as conn:
        issue = db.get_issue(conn, issue_id)
        repo = db.load_repo_info(conn).get(issue["repo"]) if issue else None
    if issue is None:
        abort(404)
    if issue["explanation"] and issue["explanation_lang"] == g.lang:
        return {"explanation": issue["explanation"]}
    if not ai.status["available"]:
        return {"explanation": None}
    try:
        text = ai.explain(issue["title"], issue["body"] or "", issue["repo"], repo["description"] if repo else "", g.lang)
    except (httpx.HTTPError, ValueError, KeyError):
        return {"explanation": None}
    if text:
        with db.connect() as conn:
            db.save_explanation(conn, issue_id, text, g.lang)
    return {"explanation": text or None}


@app.post("/notify-test")
def notify_test():
    """Send a sample notification, to see what they look like."""
    notify("Issue Radar", t("notify.test_subtitle"), t("notify.test_message"))
    return _done(tab="settings")


@app.post("/translate")
def translate_text():
    """Translate your comment: into English to post it, or into your language to read it."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", ""))[:4000]
    target = data.get("to")
    if target not in available_languages() or not text.strip():
        abort(400)
    if not ai.status["available"]:
        return {"text": None}
    try:
        result = ai.translate(text, "comment on a GitHub issue", target)
    except (httpx.HTTPError, ValueError, KeyError):
        result = ""
    return {"text": result or None}


@app.post("/issues/<int:issue_id>/skip")
def skip(issue_id: int):
    with db.connect() as conn:
        db.set_status(conn, issue_id, "skipped")
    return _done(undo_issue=issue_id)


@app.post("/issues/<int:issue_id>/restore")
def restore(issue_id: int):
    """Put an issue back in the "new" list (undo a skip, or give up on an issue)."""
    with db.connect() as conn:
        db.set_status(conn, issue_id, "new")
    return _done(tab=request.form.get("tab", "new"))


@app.post("/repos/block")
def block():
    repo = request.form["repo"]
    with db.connect() as conn:
        db.block_repo(conn, repo)
    return _done(undo_repo=repo)


@app.post("/repos/unblock")
def unblock():
    with db.connect() as conn:
        db.unblock_repo(conn, request.form["repo"])
    return _done(tab=request.form.get("tab", "new"))
