"""Rebuild the test fixture and its golden output.

    uv run python tests/make_fixture.py

Both files are written from the data in tests/helpers.py, so running this twice
changes nothing. Refresh it when the planner is supposed to produce a new plan.
"""

from __future__ import annotations

from solver import load_workbook, solve
from tests.helpers import EXPECTED, FIXTURE, make_fixture, read_expected, write_expected


def main() -> int:
    path = make_fixture()
    data = load_workbook(path)
    plan = solve(data)
    write_expected(EXPECTED, data, plan)

    print(f"fixture   {path}")
    print(f"expected  {EXPECTED}")
    print(f"sessions  {len(plan.sessions)}  unresolved {len(plan.unresolved)}")
    print(f"open weeks {list(data.open_weeks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
