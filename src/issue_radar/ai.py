"""AI summaries with a model running on your own computer, through Ollama.

Nothing here is required: if Ollama isn't installed or running, issues are
shown without summaries. Choose another model with the OLLAMA_MODEL
environment variable (default: gemma3:4b).
"""

import json
import os
import re
import unicodedata
import threading

import httpx

from issue_radar import db
from issue_radar.github import issue_body
from issue_radar.i18n import DEFAULT_LANGUAGE

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")

BATCH_SIZE = 10  # issues summarized per round, to keep the computer responsive
IDLE_WAIT = 10 * 60  # seconds to wait when there is nothing to summarize

# Kept small so the model fits on computers with 8 GB of memory.
BODY_LIMIT = 2000  # characters of the issue's description sent to the model
CONTEXT_SIZE = 2048  # tokens the model keeps in memory
KEEP_LOADED = "30s"  # free the model's memory soon after the last summary

# Issues that couldn't be summarized since the program started; not retried
# until the next start, so one stubborn issue can't keep the computer busy.
_failed: set[int] = set()

# Bump this when the instructions change, so older summaries are written again.
SUMMARY_VERSION = 4

# With a description shorter than this, the title already says it all.
SHORT_BODY = 200

# Language names the model understands, by interface language code.
_LANGUAGE_NAMES = {"tr": "Turkish", "en": "English"}

# Read by the web page: is there a model to make summaries with?
status = {"available": False, "state": "no_ollama"}  # state: on | no_ollama | no_model

# Set this to summarize right away, e.g. after a scan found new issues.
wake = threading.Event()

_ANSWER_FORMAT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}

# Only a summary: we tried asking the small model how hard an issue is, and its
# answers swung with the wording (all "medium", then all "easy"). The kind of
# work (docs, tests, translation) comes from plain rules in kinds.py instead.
_INSTRUCTIONS = """\
You help people who are new to open source pick a GitHub issue to work on.
Read the issue and answer in JSON with one field:

- summary: at most two short sentences in {language}, in plain words, saying
  what needs to change and where. {address}
  Don't repeat the title; say what the title doesn't. Keep code names, file
  names, commands and product terms (like "player", "docs", "CLI") as they are,
  in `backticks` if they are code. Only use what the issue says; never guess.
"""

# How to talk to the reader, per language.
_ADDRESS = {
    "tr": (
        'Use the informal "sen" verb forms, like "eklemelisin" or "bakabilirsin" '
        '(never "siz" or "biz" forms), but don\'t write the word "Sen" itself.'
    ),
    "en": 'Speak to the reader directly ("you").',
}

# Small models sometimes answer in English anyway. Turkish text usually has
# Turkish letters or words; short text may have neither ("Birim testlerini ekle"),
# so then we look for common English words instead.
_TURKISH_HINTS = ("ç", "ğ", "ı", "ö", "ş", "ü", " ve ", " bir ", " için ", " bu ")
_ENGLISH_WORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "is", "are", "be",
    "add", "fix", "update", "remove", "make", "use", "when", "should", "not", "it", "this", "that",
}


def _looks_turkish(text: str) -> bool:
    padded = f" {text.lower()} "
    if any(hint in padded for hint in _TURKISH_HINTS):
        return True
    words = {word.strip(".,:;!?()'\"") for word in text.lower().split()}
    return not words & _ENGLISH_WORDS


def _in_language(text: str, lang: str) -> bool:
    if lang == "tr":
        return _looks_turkish(text)
    if lang == "en":
        # Turkish letters in an "English" answer mean the model didn't translate.
        return not any(letter in text.lower() for letter in "çğışöü")
    return True


def _repeats_title(summary: str, title: str) -> bool:
    """True if nearly every word of the summary is already in the title."""
    words = lambda text: {w.strip(".,:;!?`'\"()[]").lower() for w in text.split()} - {""}
    summary_words = words(summary)
    return len(summary_words) > 0 and len(summary_words & words(title)) / len(summary_words) > 0.7


def check() -> str:
    """"on" if Ollama is running and has the model; otherwise "no_ollama" or "no_model"."""
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        return "no_ollama"
    names = {model["name"] for model in response.json().get("models", [])}
    return "on" if MODEL in names or f"{MODEL}:latest" in names else "no_model"


def is_available() -> bool:
    return check() == "on"


def _ask(title: str, body: str, repo: str, lang: str) -> dict:
    language = _LANGUAGE_NAMES.get(lang, "English")
    instructions = _INSTRUCTIONS.format(language=language, address=_ADDRESS.get(lang, _ADDRESS["en"]))
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "format": _ANSWER_FORMAT,
            "keep_alive": KEEP_LOADED,
            "options": {"temperature": 0.2, "num_ctx": CONTEXT_SIZE},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": f"Repository: {repo}\nTitle: {title}\n\n{body[:BODY_LIMIT]}"},
            ],
        },
        # The first answer can be slow while the model loads into memory.
        timeout=300,
    )
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])


def summarize(title: str, body: str, repo: str, lang: str) -> str:
    """Ask the model for a short summary.

    Returns "" when a summary wouldn't help: the description is too short to
    add anything to the title (then the model isn't asked at all), the model
    answered in the wrong language twice, or the summary only repeats the title.
    """
    if len(body.strip()) < SHORT_BODY:
        return ""
    summary = str(_ask(title, body, repo, lang).get("summary", "")).strip()
    if summary and not _in_language(summary, lang):
        summary = str(_ask(title, body, repo, lang).get("summary", "")).strip()  # one more try

    if not _in_language(summary, lang) or _repeats_title(summary, title):
        return ""
    return summary


def _summarize_batch() -> int:
    """Summarize up to BATCH_SIZE issues. Returns how many were done."""
    with db.connect() as conn:
        lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
        issues = db.issues_to_summarize(conn, lang, SUMMARY_VERSION, BATCH_SIZE + len(_failed))
    issues = [issue for issue in issues if issue["id"] not in _failed][:BATCH_SIZE]

    done = 0
    for issue in issues:
        body = issue["body"]
        if body is None:  # saved before we kept descriptions
            try:
                body = issue_body(issue["url"])
            except httpx.HTTPError:
                body = ""
            with db.connect() as conn:
                db.set_body(conn, issue["id"], body)

        try:
            summary = summarize(issue["title"], body, issue["repo"], lang)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Couldn't summarize ({issue['url']}): {error}", flush=True)
            _failed.add(issue["id"])
            continue

        # Talking to the model takes a while; only open the database to save.
        with db.connect() as conn:
            db.save_summary(conn, issue["id"], summary, lang, SUMMARY_VERSION)
        done += 1
    return done


_TRANSLATE_INSTRUCTIONS = """\
Translate this {kind} into {language}. Write natural {language}, as a person
would, not word for word. {address} Keep exactly as they are: code, file names,
function and class names, commands, version numbers, product and project names,
issue numbers like #123, @mentions, links, and anything in `backticks` or
[square brackets]. Translate every ordinary word, even one that looks like a name.
Sentences already in {language} stay exactly as they are. Keep the same line
breaks. Answer in JSON with one field: "translation".
"""

_TRANSLATE_ADDRESS = {
    "tr": 'For instructions use the informal "sen" form, like "ekle" or "düzelt", never "ekleyin".',
    "en": "Keep the friendly, polite tone of a message to open-source maintainers.",
}

# Tags some projects put before titles: "[Bug] ", "[Good First Issue]: ".
_TITLE_TAGS = re.compile(r"^(?:\s*\[[^\]]{1,40}\]:?)+\s*")
# Beginner labels repeated at the end: "(good-first-issue)", "(Hacktoberfest)".
_TITLE_LABELS = re.compile(
    r"\s*\((?:good[ -]first[ -]issue|first[ -]timers?[ -]only|beginner(?:[ -]friendly)?|help[ -]wanted|hacktoberfest)\)\s*$",
    re.IGNORECASE,
)


def _clean_title(title: str) -> str:
    """The words of a title without tags, labels and emoji, which the model
    tends to translate too ("🐉" -> "Dragon"). The original title keeps them."""
    text = _TITLE_LABELS.sub("", _TITLE_TAGS.sub("", title))
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Cf") and c not in "\ufe0e\ufe0f")
    return re.sub(r"\s{2,}", " ", text).strip() or title


def needs_translation(text: str, lang: str) -> bool:
    """True if the text isn't already in the interface language."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:  # "🐞" and the like
        return False
    if lang == "tr":
        return not _in_language(text, "tr")
    # For English: translate text that is mostly in another script (Chinese, Russian…).
    return sum(not c.isascii() for c in letters) / len(letters) > 0.3


def translate(text: str, kind: str, lang: str) -> str:
    """The text in the interface language, or "" if the model's answer won't do."""
    language = _LANGUAGE_NAMES.get(lang, "English")
    instructions = _TRANSLATE_INSTRUCTIONS.format(kind=kind, language=language, address=_TRANSLATE_ADDRESS.get(lang, ""))
    if "title" in kind:
        text = _clean_title(text)
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "format": {"type": "object", "properties": {"translation": {"type": "string"}}, "required": ["translation"]},
            "keep_alive": KEEP_LOADED,
            "options": {"temperature": 0.1, "num_ctx": CONTEXT_SIZE},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": text},
            ],
        },
        timeout=300,
    )
    response.raise_for_status()
    result = str(json.loads(response.json()["message"]["content"]).get("translation", "")).strip()
    # Throw away answers in the wrong language, or ones that wander off (far longer than the original).
    if not result or not _in_language(result, lang) or len(result) > 2 * len(text) + 40:
        return ""
    return result


def _translate_batch() -> int:
    """Translate up to BATCH_SIZE titles and project descriptions on the list
    into the interface language. Returns how many were done."""
    with db.connect() as conn:
        lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
        done_already = db.load_translations(conn, lang)
        todo = [
            (kind, text) for kind, text in db.texts_on_the_list(conn)
            if text not in done_already and needs_translation(text, lang)
        ][:BATCH_SIZE]

    for kind, text in todo:
        try:
            translation = translate(text, "GitHub issue title" if kind == "title" else "project description", lang)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Couldn't translate: {error}", flush=True)
            translation = ""
        with db.connect() as conn:
            db.save_translation(conn, text, lang, translation)
    return len(todo)


def summarize_forever() -> None:
    """Keep summarizing and translating new issues in the background, one at a time."""
    while True:
        status["state"] = check()
        status["available"] = status["state"] == "on"
        done = _summarize_batch() + _translate_batch() if status["available"] else 0
        if done == 0:
            wake.wait(IDLE_WAIT)
            wake.clear()


def failed_ids() -> set[int]:
    """Issues whose summary failed; the page stops saying "in progress" for them."""
    return set(_failed)


_EXPLAIN_INSTRUCTIONS = """\
Explain this GitHub issue to someone making their first open-source contribution.
Write 3 or 4 short sentences in {language}, in plain words: what is wrong or
missing, why it matters for the project, and what a fix probably involves.
{address} Only use what the issue says; if something isn't clear from the
issue, say so instead of guessing. Keep code names as they are, in `backticks`.
Answer in JSON with one field: "explanation".
"""


def explain(title: str, body: str, repo: str, about: str, lang: str) -> str:
    """A plain explanation of the issue for the issue guide; "" if it didn't work out."""
    language = _LANGUAGE_NAMES.get(lang, "English")
    instructions = _EXPLAIN_INSTRUCTIONS.format(language=language, address=_ADDRESS.get(lang, _ADDRESS["en"]))
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "format": {"type": "object", "properties": {"explanation": {"type": "string"}}, "required": ["explanation"]},
            "keep_alive": KEEP_LOADED,
            "options": {"temperature": 0.2, "num_ctx": CONTEXT_SIZE},
            "messages": [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": f"Repository: {repo}\nAbout the project: {about}\nTitle: {title}\n\n{body[:BODY_LIMIT]}",
                },
            ],
        },
        timeout=300,
    )
    response.raise_for_status()
    text = str(json.loads(response.json()["message"]["content"]).get("explanation", "")).strip()
    return text if _in_language(text, lang) else ""
