"""User settings from the settings page, stored in the database."""

import sqlite3

from issue_radar import db, github
from issue_radar.languages import SUPPORTED_LANGUAGES

DEFAULT_LANGUAGES = ["python", "javascript"]
DEFAULT_MIN_STARS = 100
MIN_STARS_CHOICES = [0, 50, 100, 500, 1000]


def search_languages(conn: sqlite3.Connection) -> list[str]:
    saved = db.get_setting(conn, "search_languages")
    if saved is None:
        return DEFAULT_LANGUAGES
    return [lang for lang in saved.split(",") if lang in SUPPORTED_LANGUAGES]


def languages_were_chosen(conn: sqlite3.Connection) -> bool:
    return db.get_setting(conn, "search_languages") is not None


def min_stars(conn: sqlite3.Connection) -> int:
    saved = db.get_setting(conn, "min_stars")
    return int(saved) if saved is not None else DEFAULT_MIN_STARS


def save(conn: sqlite3.Connection, languages: list[str], stars: int) -> None:
    if stars not in MIN_STARS_CHOICES:
        raise ValueError(f"Minimum stars must be one of {MIN_STARS_CHOICES}.")
    save_languages(conn, languages)
    db.set_setting(conn, "min_stars", str(stars))


def save_languages(conn: sqlite3.Connection, languages: list[str]) -> None:
    languages = [lang for lang in SUPPORTED_LANGUAGES if lang in languages]
    if not languages:
        raise ValueError("Pick at least one language.")
    db.set_setting(conn, "search_languages", ",".join(languages))


def languages_from_github() -> list[str] | None:
    """Pick the languages you use on GitHub and save them.

    Returns them, or None if we aren't signed in to GitHub or found none
    we can search (say, only HTML pages). Talks to GitHub before opening
    the database, so the scanner isn't kept waiting.
    """
    login = github.whoami()
    if not login:
        return None
    with db.connect() as conn:
        contributed = db.load_contributions(conn)
    if contributed is None:
        contributed = github.contributed_repos()
    most_first = sorted(contributed, key=contributed.get, reverse=True)
    languages = github.guess_languages(login, most_first)
    if not languages:
        return None
    with db.connect() as conn:
        save_languages(conn, languages)
    return languages
