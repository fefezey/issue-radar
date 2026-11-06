"""The web page, in both languages, with the data the scanner would have saved."""

import json
import re
import string
from pathlib import Path

import pytest

from conftest import make_issue
from issue_radar import db, settings
from issue_radar.i18n import available_languages, translate
from issue_radar.web import app, code

LOCALES = Path(__file__).parent.parent / "src" / "issue_radar" / "locales"
TABS = ["", "?tab=interested", "?tab=hidden", "?tab=settings", "?easy=1"]


@pytest.fixture
def client():
    with db.connect() as conn:
        db.save_issues(conn, [make_issue(1), make_issue(2), make_issue(3, title="Fix typo in docs")], "python")
        db.save_issues(conn, [make_issue(4, repo="other/repo")], "javascript")
        db.save_summary(conn, 1, "`a.py` dosyasını güncellemelisin.", "tr", 4)
        db.set_status(conn, 4, "interested")
        db.save_progress(conn, 4, "assigned", None)
    return app.test_client()


@pytest.mark.parametrize("language", ["tr", "en"])
@pytest.mark.parametrize("tab", TABS)
def test_every_page_opens(client, language, tab):
    with db.connect() as conn:
        db.set_setting(conn, "language", language)
    response = client.get("/" + tab)
    assert response.status_code == 200
    assert f'<html lang="{language}">' in response.get_data(as_text=True)


def test_new_issues_are_grouped_by_project(client):
    page = client.get("/").get_data(as_text=True)
    assert page.count('<section class="project"') == 1  # owner/project; other/repo's issue is in Interested
    assert "<details class=\"more\">" in page
    assert "<code>a.py</code>" in page


def test_interested_issue_shows_progress_and_the_fixes_line(client):
    page = client.get("/?tab=interested").get_data(as_text=True)
    assert 'aria-current="step"' in page
    assert "Fixes #4" in page


def test_buttons_work_with_and_without_javascript(client):
    assert client.post("/issues/1/skip", headers={"X-Requested-With": "fetch"}).status_code == 204
    with db.connect() as conn:
        assert db.get_issue(conn, 1)["status"] == "skipped"
    response = client.post("/issues/1/restore")
    assert response.status_code == 302
    with db.connect() as conn:
        assert db.get_issue(conn, 1)["status"] == "new"


def test_settings_need_at_least_one_language(client):
    response = client.post("/settings", data={"min_stars": "100"})
    assert "error=no_language" in response.headers["Location"]


def test_code_filter_escapes_html():
    assert str(code("`x` <b>y</b>")) == "<code>x</code> &lt;b&gt;y&lt;/b&gt;"


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_language_has_every_text_with_the_same_placeholders():
    english = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    base = lambda key: re.sub(r"\.(one|other)$", "", key)
    english_by_base = {base(k): v for k, v in english.items() if not k.endswith(".one")}
    for language in available_languages():
        texts = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
        assert {base(k) for k in english} <= {base(k) for k in texts}, f"{language} is missing texts"
        for key, text in texts.items():
            if key.endswith(".one"):
                continue
            assert _placeholders(text) == _placeholders(english_by_base[base(key)]), f"{language}: {key}"


def test_plural_forms():
    assert translate("en", "issue.stars", 1, stars="1") == "1 star"
    assert translate("en", "issue.stars", 3, stars="3") == "3 stars"
    assert translate("tr", "issue.stars", 3, stars="3") == "3 yıldız"


def test_translated_title_shows_with_the_original_underneath(client):
    with db.connect() as conn:
        db.set_setting(conn, "language", "tr")
        db.save_translation(conn, "Issue 1", "tr", "1 numaralı iş")
    page = client.get("/").get_data(as_text=True)
    assert "1 numaralı iş</a></h2>" in page
    assert '<p class="original" lang="en">Issue 1</p>' in page


def test_comment_translation_needs_the_ai(client, monkeypatch):
    from issue_radar import ai

    monkeypatch.setitem(ai.status, "available", False)
    assert client.post("/translate", json={"text": "Merhaba", "to": "en"}).get_json() == {"text": None}
    assert client.post("/translate", json={"text": "", "to": "en"}).status_code == 400
    assert client.post("/translate", json={"text": "Hi", "to": "xx"}).status_code == 400

    monkeypatch.setitem(ai.status, "available", True)
    monkeypatch.setattr(ai, "translate", lambda text, kind, lang: "I'd like to work on this.")
    assert client.post("/translate", json={"text": "Bu işi almak istiyorum.", "to": "en"}).get_json() == {
        "text": "I'd like to work on this."
    }


def test_test_notification_button(client, monkeypatch):
    import issue_radar.web as web

    sent = []
    monkeypatch.setattr(web, "notify", lambda *parts: sent.append(parts))
    assert client.post("/notify-test", headers={"X-Requested-With": "fetch"}).status_code == 204
    assert sent and sent[0][0] == "Issue Radar"
    assert "data-notify-test" in client.get("/?tab=settings").get_data(as_text=True)


def test_languages_from_github(client, monkeypatch):
    import issue_radar.web as web
    from issue_radar import github

    monkeypatch.setattr(web, "_github_login", {})
    monkeypatch.setattr(github, "whoami", lambda: "me")
    monkeypatch.setattr(github, "guess_languages", lambda login, contributed: ["c", "typescript"])
    monkeypatch.setattr(github, "contributed_repos", lambda: {})
    page = client.get("/?tab=settings").get_data(as_text=True)
    assert "gh auth login" not in page and "/languages/from-github" in page

    response = client.post("/languages/from-github")
    assert "picked=1" in response.headers["Location"]
    with db.connect() as conn:
        assert set(settings.search_languages(conn)) == {"c", "typescript"}

    monkeypatch.setattr(github, "guess_languages", lambda login, contributed: [])
    assert "error=github_languages" in client.post("/languages/from-github").headers["Location"]


def test_first_run_picks_languages_only_once(monkeypatch):
    from issue_radar import scanner

    monkeypatch.setattr(scanner, "_looked_at_github_languages", False)
    monkeypatch.setattr(settings, "languages_from_github", lambda: ["go"])
    with db.connect() as conn:
        settings.save_languages(conn, ["rust"])  # you picked these yourself
    scanner.pick_languages_on_first_run()
    with db.connect() as conn:
        assert settings.search_languages(conn) == ["rust"]
