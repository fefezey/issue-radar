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

DIFFICULTIES = ["easy", "medium", "hard"]
EFFORTS = ["under_1h", "1_3h", "3_8h", "over_1d"]

# Language names the model understands, by interface language code.
_LANGUAGE_NAMES = {"tr": "Turkish", "en": "English"}

# Read by the web page: is there a model to make summaries with?
status = {"available": False}

# Set this to summarize right away, e.g. after a scan found new issues.
wake = threading.Event()

_ANSWER_FORMAT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "difficulty": {"type": "string", "enum": DIFFICULTIES},
        "effort": {"type": "string", "enum": EFFORTS},
    },
    "required": ["summary", "difficulty", "effort"],
}

_INSTRUCTIONS = """\
You help people who are new to open source pick a GitHub issue to work on.
Read the issue and answer in JSON with these fields:

- summary: two short sentences in {language}, in plain words, saying what needs
  to be done. Keep code names, file names and technical terms as they are.
  Only use what the issue says; don't make up details.
- difficulty: for someone making one of their first contributions.
  "easy": a small, clear change. "medium": needs some understanding of the code.
  "hard": needs deep knowledge of the project or the topic.
- effort: rough time for a beginner: "under_1h", "1_3h", "3_8h" or "over_1d".
"""


def is_available() -> bool:
    """True if Ollama is running and has the model."""
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    names = {model["name"] for model in response.json().get("models", [])}
    return MODEL in names or f"{MODEL}:latest" in names


def summarize(title: str, body: str, repo: str, lang: str) -> dict:
    """Ask the model for a summary, difficulty and effort estimate."""
    language = _LANGUAGE_NAMES.get(lang, "English")
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "format": _ANSWER_FORMAT,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": _INSTRUCTIONS.format(language=language)},
                {"role": "user", "content": f"Repository: {repo}\nTitle: {title}\n\n{body}"},
            ],
        },
        # The first answer can be slow while the model loads into memory.
        timeout=300,
    )
    response.raise_for_status()
    answer = json.loads(response.json()["message"]["content"])

    summary = str(answer.get("summary", "")).strip()
    if not summary:
        raise ValueError("The model returned an empty summary.")
    return {
        "summary": summary,
        "difficulty": answer.get("difficulty") if answer.get("difficulty") in DIFFICULTIES else "medium",
        "effort": answer.get("effort") if answer.get("effort") in EFFORTS else "1_3h",
    }


def _summarize_batch() -> int:
    """Summarize up to BATCH_SIZE issues. Returns how many were done."""
    with db.connect() as conn:
        lang = db.get_setting(conn, "language") or DEFAULT_LANGUAGE
        issues = db.issues_to_summarize(conn, lang, BATCH_SIZE)

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
            result = summarize(issue["title"], body, issue["repo"], lang)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Özet hazırlanamadı ({issue['url']}): {error}", flush=True)
            continue

        # Talking to the model takes a while; only open the database to save.
        with db.connect() as conn:
            db.save_summary(conn, issue["id"], result["summary"], result["difficulty"], result["effort"], lang)
        done += 1
    return done


def summarize_forever() -> None:
    """Keep summarizing new issues in the background, one at a time."""
    while True:
        status["available"] = is_available()
        done = _summarize_batch() if status["available"] else 0
        if done == 0:
            wake.wait(IDLE_WAIT)
            wake.clear()
