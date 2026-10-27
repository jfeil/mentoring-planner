"""Fixtures. Everything is written into tmp_path, so no test can leave state behind."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import FIXTURE, PEERS, write_workbook  # noqa: E402
from solver import load_workbook, solve  # noqa: E402


@pytest.fixture
def workbook(tmp_path: Path) -> Path:
    """The example input workbook, rebuilt for each test."""

    return write_workbook(tmp_path / "input.xlsx")


@pytest.fixture
def data(workbook: Path):
    return load_workbook(workbook)


@pytest.fixture
def plan(data):
    return solve(data)


@pytest.fixture
def committed_fixture() -> Path:
    """The workbook that lives in tests/fixtures, for readers of the repo."""

    assert FIXTURE.exists(), "run: uv run python -m tests.make_fixture"
    return FIXTURE


def peers_without_topic(topic: str) -> list:
    return [peer for peer in PEERS if peer[1] != topic]
