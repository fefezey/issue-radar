"""Plain rules: kinds of work, contributing guides, AI answer checks."""

import pytest

from issue_radar import ai
from issue_radar.claiming import DRAFT, PLAN_PLACEHOLDER, policy_from_guide
from issue_radar.kinds import kind_of


@pytest.mark.parametrize(
    "title, labels, expected",
    [
        ("Translate the snowflake icon's aria-label", [], "translation"),
        ("Fix typo in README", [], "docs"),
        ("Add pickle round-trip tests for OneFitModel", [], "tests"),
        ("Fix the thing", ["good first issue", "Documentation"], "docs"),
        ("Fix the thing", ["type::documentation"], "docs"),
        ("Fix the thing", ["area/i18n"], "translation"),
        ("Crash when saving a file", ["bug"], None),
        # Words that only look like the rules' words.
        ("Use the latest contest data", [], None),
        ("Protest page crashes", [], None),
        ("Documented behaviour differs", [], None),
    ],
)
def test_kind_of(title, labels, expected):
    assert kind_of(title, labels) == expected


@pytest.mark.parametrize(
    "guide, expected",
    [
        ("As a general rule, we don’t assign issues to anyone", "no_claim"),  # curly apostrophe
        ("We do not assign issues; just open a PR.", "no_claim"),
        ("No need to ask, feel free to open a pull request", "no_claim"),
        ("Comment asking for the Issue to be assigned to you", "ask"),
        ("Please don't open a PR before being assigned", "ask"),
        ("", "ask"),
    ],
)
def test_policy_from_guide(guide, expected):
    assert policy_from_guide(guide) == expected


def test_draft_asks_for_your_own_plan():
    assert PLAN_PLACEHOLDER in DRAFT
    assert "assign" in DRAFT


def test_turkish_check():
    assert ai._in_language("Bu dosyayı güncellemelisin.", "tr")
    assert not ai._in_language("Update the docs.", "tr")
    assert ai._in_language("Update the docs.", "en")


def test_summary_that_repeats_the_title_is_caught():
    assert ai._repeats_title("Add lead time to power approximation.", "add lead time to power approximation")
    assert not ai._repeats_title("`player.js` dosyasındaki fonksiyonu güncellemelisin.", "Race condition in player")


def test_short_description_gets_no_summary_and_no_model_call(monkeypatch):
    def no_model(*args, **kwargs):
        raise AssertionError("the model shouldn't be asked")

    monkeypatch.setattr(ai, "_ask", no_model)
    assert ai.summarize("Add lead time", "Short body.", "owner/project", "tr") == ""


def test_summary_in_the_wrong_language_is_retried_then_dropped(monkeypatch):
    answers = iter([{"summary": "Update the docs."}, {"summary": "Update the parser to handle empty files."}])
    monkeypatch.setattr(ai, "_ask", lambda *args: next(answers))
    assert ai.summarize("Title", "x" * 300, "owner/project", "tr") == ""


def test_good_summary_is_kept(monkeypatch):
    monkeypatch.setattr(ai, "_ask", lambda *args: {"summary": "`player.js` dosyasını güncellemelisin."})
    assert ai.summarize("Race condition", "x" * 300, "owner/project", "tr") == "`player.js` dosyasını güncellemelisin."


def test_what_needs_translating():
    assert ai.needs_translation("Add unit tests for GrpcStatus", "tr")
    assert not ai.needs_translation("Birim testlerini ekle", "tr")
    assert not ai.needs_translation("🐞", "tr")
    assert not ai.needs_translation("Add unit tests", "en")
    assert ai.needs_translation("文档和 CI 跟进默认分支改名", "en")


def test_translation_drops_title_tags_and_bad_answers(monkeypatch):
    sent = []

    class Answer:
        def __init__(self, translation):
            self.translation = translation

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"translation": "%s"}' % self.translation}}

    def fake_post(url, json):
        sent.append(json["messages"][1]["content"])
        return Answer(replies.pop(0))

    monkeypatch.setattr(ai.httpx, "post", lambda url, json, timeout: fake_post(url, json))
    replies = ["Birim testlerini ekle", "Add unit tests"]
    assert ai.translate("[Beginner]: Add unit tests", "GitHub issue title", "tr") == "Birim testlerini ekle"
    assert sent[0] == "Add unit tests"  # the "[Beginner]:" tag isn't sent
    assert ai.translate("Add unit tests", "GitHub issue title", "tr") == ""  # still English: thrown away
