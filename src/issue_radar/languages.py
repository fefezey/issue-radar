# Languages to search. Change or add to this list to see other languages.
LANGUAGES = ["python", "javascript"]

_DISPLAY_NAMES = {"javascript": "JavaScript", "typescript": "TypeScript", "php": "PHP", "c++": "C++"}


def language_name(name: str) -> str:
    """'javascript' -> 'JavaScript', 'python' -> 'Python'"""
    return _DISPLAY_NAMES.get(name, name.capitalize())
