"""AI summaries with a model running on your own computer, through Ollama.

Nothing here is required: if Ollama isn't installed or running, issues are
shown without summaries. Choose another model with the OLLAMA_MODEL
environment variable (default: gemma3:4b).
"""

import json
import os
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

# A Turkish summary should have Turkish letters or common Turkish words;
# small models sometimes answer in English anyway.
_TURKISH_HINTS = ("ç", "ğ", "ı", "ö", "ş", "ü", " ve ", " bir ", " için ", " bu ")


def _in_language(text: str, lang: str) -> bool:
    if lang != "tr":
        return True
    text = f" {text.lower()} "
    return any(hint in text for hint in _TURKISH_HINTS)


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
            print(f"Özet hazırlanamadı ({issue['url']}): {error}", flush=True)
            _failed.add(issue["id"])
            continue

        # Talking to the model takes a while; only open the database to save.
        with db.connect() as conn:
            db.save_summary(conn, issue["id"], summary, lang, SUMMARY_VERSION)
        done += 1
    return done


def summarize_forever() -> None:
    """Keep summarizing new issues in the background, one at a time."""
    while True:
        status["state"] = check()
        status["available"] = status["state"] == "on"
        done = _summarize_batch() if status["available"] else 0
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
