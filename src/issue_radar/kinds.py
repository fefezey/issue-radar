"""What kind of work an issue is, from its title and GitHub labels.

Documentation, test and translation issues are the gentlest first
contributions. We tell them apart with plain rules instead of the AI model:
small models turned out to be unreliable at judging difficulty.
"""

import re

# Kinds, in the order they are checked. Each has label names to look for
# and patterns to find in the title (matched as whole words, ignoring case).
_RULES = {
    "translation": {
        "labels": ("translation", "translations", "i18n", "l10n", "localization", "localisation"),
        "title": (r"translat\w*", r"i18n", r"l10n", r"locali[sz]\w*"),
    },
    "docs": {
        "labels": ("documentation", "docs", "doc", "typo"),
        "title": (r"docs?", r"documentation", r"readme", r"typos?", r"docstrings?", r"spelling", r"changelog"),
    },
    "tests": {
        "labels": ("tests", "test", "testing", "unit tests"),
        "title": (r"tests?", r"testing", r"test coverage", r"unit tests?"),
    },
}

_TITLE_PATTERNS = {
    kind: re.compile(r"\b(?:" + "|".join(rule["title"]) + r")\b", re.IGNORECASE)
    for kind, rule in _RULES.items()
}

KINDS = list(_RULES)


def _label_words(labels: list[str]) -> set[str]:
    """Projects write labels differently ("type::documentation", "area/docs",
    "Unit Tests"), so look at whole labels and at their separate words."""
    words = set()
    for label in labels:
        label = label.lower().strip()
        words.add(label)
        words.update(w for w in re.split(r"[^a-z0-9]+", label) if w)
    return words


def kind_of(title: str, labels: list[str]) -> str | None:
    """'docs', 'tests', 'translation', or None for anything else."""
    words = _label_words(labels)
    for kind, rule in _RULES.items():
        if words & set(rule["labels"]) or _TITLE_PATTERNS[kind].search(title):
            return kind
    return None
