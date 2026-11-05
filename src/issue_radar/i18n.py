"""Translations. Each language is a JSON file in the `locales` folder.

To add a language, copy `locales/en.json` to `locales/<code>.json`
(for example `de.json`) and translate the values.
"""

import json
from functools import cache
from importlib.resources import files

DEFAULT_LANGUAGE = "en"
_LOCALES = files("issue_radar") / "locales"


@cache
def available_languages() -> list[str]:
    return sorted(path.name.removesuffix(".json") for path in _LOCALES.iterdir() if path.name.endswith(".json"))


@cache
def _messages(language: str) -> dict[str, str]:
    return json.loads((_LOCALES / f"{language}.json").read_text(encoding="utf-8"))


def translate(language: str, key: str, count: int | None = None, **values) -> str:
    """Look up `key` in the given language and fill in `{placeholders}`.

    With `count`, uses `key.one` for 1 and `key.other` otherwise, so
    "1 star" / "3 stars" can be told apart. Missing keys fall back to English.
    """
    keys = [key]
    if count is not None:
        values["count"] = count
        keys = ([f"{key}.one"] if count == 1 else []) + [f"{key}.other", key]

    for messages in (_messages(language), _messages(DEFAULT_LANGUAGE)):
        for candidate in keys:
            if candidate in messages:
                return messages[candidate].format(**values)
    return key
