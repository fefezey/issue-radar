from datetime import datetime, timezone

from flask import Flask, abort, redirect, render_template, request, url_for

from issue_radar import db

app = Flask(__name__)


@app.template_filter("ago")
def ago(timestamp: str) -> str:
    """'2026-11-05T12:00:00Z' -> '3 saat önce'"""
    seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))} dk önce"
    if seconds < 86400:
        return f"{int(seconds // 3600)} saat önce"
    return f"{int(seconds // 86400)} gün önce"


@app.get("/")
def index():
    tab = request.args.get("tab", "new")
    if tab not in ("new", "interested"):
        tab = "new"
    with db.connect() as conn:
        issues = db.list_issues(conn, tab)
        new_count = len(db.list_issues(conn, "new"))
    return render_template("index.html", issues=issues, tab=tab, new_count=new_count)


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
    return redirect(url_for("index"))


@app.post("/repos/block")
def block():
    with db.connect() as conn:
        db.block_repo(conn, request.form["repo"])
    return redirect(url_for("index"))
