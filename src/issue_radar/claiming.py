"""Helping you claim an issue: a comment draft, and what the project's
contributing guide says about claiming.

The draft is a plain template, not AI: a small model adds nothing to a
greeting, makes you wait, and might promise things you didn't mean.
"""

import re

# The line you're meant to replace with your own sentence. Copy-paste
# comments look like spam to maintainers; one real sentence makes the difference.
PLAN_PLACEHOLDER = "[One sentence on how you plan to fix it]"

DRAFT = f"""Hi! I'd like to work on this.

My plan: {PLAN_PLACEHOLDER}

Could you assign it to me? Thanks!"""

# Phrases in contributing guides that mean "don't ask, just open a pull request".
# DONT matches "don't", "don’t" (curly apostrophe), "dont" and "do not".
_DONT = r"(?:don['’]?t|do not)"
_NO_CLAIM_PHRASES = (
    r"no need to (?:ask|comment|be assigned|claim)",
    rf"{_DONT} need to (?:ask|comment|be assigned|claim)",
    rf"(?:you )?{_DONT} have to (?:ask|comment|be assigned|claim)",
    rf"{_DONT} ask (?:to be|for) (?:assigned|assignment|permission)",
    rf"we {_DONT} (?:usually |generally |typically )?assign issues",
    r"just (?:open|send|submit) a (?:pull request|pr)",
    r"first[- ]come,? first[- ]serve",
)
_NO_CLAIM = re.compile("|".join(_NO_CLAIM_PHRASES), re.IGNORECASE)


def policy_from_guide(text: str) -> str:
    """'no_claim' if the guide says to open a pull request without asking first,
    'ask' otherwise (the usual: comment and wait to be assigned)."""
    return "no_claim" if _NO_CLAIM.search(text) else "ask"
