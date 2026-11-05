"""User settings from the settings page, stored in the database."""

import sqlite3

from issue_radar import db
from issue_radar.languages import SUPPORTED_LANGUAGES

DEFAULT_LANGUAGES = ["python", "javascript"]
DEFAULT_MIN_STARS = 100
MIN_STARS_CHOICES = [0, 50, 100, 500, 1000]


def search_languages(conn: sqlite3.Connection) -> list[str]:
    saved = db.get_setting(conn, "search_languages")
    if saved is None:
        return DEFAULT_LANGUAGES
    return [lang for lang in saved.split(",") if lang in SUPPORTED_LANGUAGES]


def min_stars(conn: sqlite3.Connection) -> int:
    saved = db.get_setting(conn, "min_stars")
    return int(saved) if saved is not None else DEFAULT_MIN_STARS


def save(conn: sqlite3.Connection, languages: list[str], stars: int) -> None:
    languages = [lang for lang in SUPPORTED_LANGUAGES if lang in languages]
    if not languages:
        raise ValueError("Pick at least one language.")
    if stars not in MIN_STARS_CHOICES:
        raise ValueError(f"Minimum stars must be one of {MIN_STARS_CHOICES}.")
    db.set_setting(conn, "search_languages", ",".join(languages))
    db.set_setting(conn, "min_stars", str(stars))
