"""Plan the mentoring sessions.

    uv run python main.py                     # write example/input.xlsx and plan it
    uv run python main.py path/to/input.xlsx  # plan your own workbook
    uv run python main.py input.xlsx --out plan.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from solver import UnfeasibleError, WorkbookError, load_workbook, solve
from solver.report import write_plan
from solver.sample import write_sample_workbook

DEFAULT_INPUT = Path("example/input.xlsx")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"workbook with the Groups, Peers and Calendar sheets (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write the plan to this file instead of back into the input workbook",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="create an example input workbook and stop",
    )
    args = parser.parse_args(argv)

    if args.sample:
        path = write_sample_workbook(args.workbook)
        print(f"example workbook written to {path}")
        return 0

    if not args.workbook.exists():
        print(f"I cannot find {args.workbook}. Run with --sample to create an example.", file=sys.stderr)
        return 2

    try:
        data = load_workbook(args.workbook)
        plan = solve(data)
    except (WorkbookError, UnfeasibleError) as error:
        print(f"{args.workbook}: {error}", file=sys.stderr)
        return 2

    target = write_plan(args.workbook, data, plan, args.out)
    _print_summary(data, plan, target)
    return 0 if plan.complete else 1


def _print_summary(data, plan, target: Path) -> None:
    print(f"{len(plan.sessions)} session(s) across week(s) "
          f"{', '.join(str(w) for w in sorted(plan.week_loads()))}")
    for topic in data.topics:
        low, high = plan.spread(topic)
        peers = len(data.peers_for(topic))
        print(f"  {topic:<22} {peers} peer(s), sessions per peer {low}-{high}")
    for note in plan.notes:
        print(f"note: {note}")
    if plan.complete:
        print(f"plan written to {target} (sheets Plan, Sessions, Loads, Overview, Notes)")
    else:
        pairs = ", ".join(f"{g}/{t}" for g, t in plan.unresolved)
        print(f"INCOMPLETE - no open week for: {pairs}", file=sys.stderr)
        print(f"details written to {target}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
