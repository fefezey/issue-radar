from datetime import datetime, timezone

from flask import Flask, abort, redirect, render_template, request, url_for

from issue_radar import db
from issue_radar.languages import language_name
from issue_radar.scanner import status

app = Flask(__name__)
app.add_template_filter(language_name, "language")

TABS = ("new", "interested", "hidden")


def scan_text() -> str:
    if status["scanning"]:
        return "İlk tarama yapılıyor…" if status["last_scan"] is None else "Taranıyor…"
    if status["error"]:
        return "Son tarama başarısız, tekrar denenecek"
    if status["last_scan"] is None:
        return "Tarama bekleniyor"
    minutes = int((datetime.now(timezone.utc) - status["last_scan"]).total_seconds() // 60)
    return "Son tarama az önce" if minutes == 0 else f"Son tarama {minutes} dk önce"


@app.template_filter("ago")
def ago(timestamp: str) -> str:
    """'2026-11-05T12:00:00Z' -> '3 saat önce'"""
    seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} dk önce"
    if seconds < 86400:
        return f"{int(seconds // 3600)} saat önce"
    return f"{int(seconds // 86400)} gün önce"


@app.template_filter("stars")
def stars(count: int) -> str:
    """1234 -> '1.2k'"""
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


@app.get("/")
def index():
    tab = request.args.get("tab", "new")
    if tab not in TABS:
        tab = "new"
    with db.connect() as conn:
        new_issues = db.list_issues(conn, "new")
        interested_issues = db.list_issues(conn, "interested")
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
        scan_text=scan_text(),
        scanning=status["scanning"],
        scan_failed=bool(status["error"]),
    )


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
