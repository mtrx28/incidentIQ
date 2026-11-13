"""The README's generated result tables must equal what scripts/make_readme_tables.py prints."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def tables():
    spec = importlib.util.spec_from_file_location(
        "make_readme_tables", ROOT / "scripts" / "make_readme_tables.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["results", "redaction", "retrieval", "paired", "redaction-doc"])
def test_generated_block_matches_results_files(tables, name):
    path = tables.BLOCK_FILES[name]
    found = tables.extract(path.read_text(encoding="utf-8"), name)
    assert found is not None, f"{path.name} has no generated block named {name!r}"
    assert found == tables.block(name), (
        f"{path.name} is out of date; run `python scripts/make_readme_tables.py --write`")


def test_results_table_has_every_version(tables):
    text = tables.results_table()
    for run in tables.RUNS:
        assert f"[{run}]" in text
