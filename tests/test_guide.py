"""The issue guide: commands from a project's docs, files named in an issue."""

from issue_radar.guide import find_commands, find_files, name_candidates

CONTRIBUTING = """
## Getting started

```bash
$ git clone https://github.com/owner/project.git
$ pip install -e ".[dev]"
```

Run the tests:

```console
pytest
pytest -m slow
```
"""

README = """
## Usage

```bash
pip install project
conda install <package-name>
project --help
```

```python
import project  # not a shell block
```
"""


def test_commands_for_contributors_come_from_shell_blocks():
    commands = find_commands(CONTRIBUTING, README)
    assert commands["setup"] == ["git clone https://github.com/owner/project.git", 'pip install -e ".[dev]"']
    assert commands["test"] == ["pytest", "pytest -m slow"]


def test_usage_examples_are_not_setup_steps():
    commands = find_commands(README)
    assert commands == {"setup": [], "test": []}


TREE = [
    "src/project/models/reference_window_model.py",
    "src/project/models/one_fit_model.py",
    "tests/models/test_pickling.py",
    "tests/stats/test_pickling.py",
    "docs/api/models.rst",
    "node_modules/lib/one_fit_model.js",
    "src/translations/en.json",
]


def test_files_named_in_the_issue_are_found():
    paths, identifiers = name_candidates(
        "Add pickle tests for ReferenceWindowModel and OneFitModel",
        "See `tests/models/test_pickling.py` and update `en.json`.",
    )
    files = find_files(TREE, paths, identifiers)
    assert files[:2] == ["src/translations/en.json", "tests/models/test_pickling.py"]
    assert "src/project/models/reference_window_model.py" in files
    assert "src/project/models/one_fit_model.py" in files


def test_a_path_with_folders_matches_only_that_folder():
    paths, identifiers = name_candidates("", "See `tests/models/test_pickling.py`.")
    assert find_files(TREE, paths, identifiers) == ["tests/models/test_pickling.py"]


def test_folder_names_and_docs_are_not_matched_as_code():
    paths, identifiers = name_candidates("", "Look at `tests/models/test_pickling.py`")
    assert "models" not in identifiers
    assert "docs/api/models.rst" not in find_files(TREE, paths, {"models"})


def test_vendored_files_are_skipped():
    assert find_files(TREE, set(), {"OneFitModel"}) == ["src/project/models/one_fit_model.py"]
