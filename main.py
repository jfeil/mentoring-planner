"""Plan the mentoring sessions.

    uv run python main.py                     # write example/input.xlsx and plan it
    uv run python main.py path/to/input.xlsx  # plan your own workbook
    uv run python main.py input.xlsx --out plan.xlsx
    uv run python main.py --new template.xlsx --classes 6a:2 6b:2 --topics Reading Maths
    uv run python main.py --app               # open the browser front end

The same file is the entry point of the bundled executable: run mentoring-planner.exe
with no arguments and it serves the browser front end.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

from solver import UnfeasibleError, WorkbookError, load_workbook, solve
from solver.report import write_plan
from solver.sample import write_sample_workbook
from solver.scaffold import Spec, mondays, parse_classes, write_scaffold

TEN_WEEKS_AHEAD = 10


def default_workbook() -> Path:
    """Where to look when no workbook is named.

    In the bundled exe that is the folder of the exe itself, so a double click on
    a sheet sitting next to it works, and an unprompted run does not try to write
    into whatever directory windows happens to start the process from.
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "input.xlsx"
    return Path("example/input.xlsx")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "workbook",
        nargs="?",
        type=Path,
        default=None,
        help=f"workbook with the Groups, Peers and Calendar sheets (default: {default_workbook()})",
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
    parser.add_argument(
        "--new",
        action="store_true",
        help="create an empty template workbook and stop (see --classes/--topics/--weeks)",
    )
    parser.add_argument(
        "--classes",
        nargs="+",
        metavar="CLASS:SPLITS",
        help="tutored classes and how many groups each is split into, e.g. 6a:2 6b:3",
    )
    parser.add_argument(
        "--peer-classes",
        nargs="+",
        metavar="CLASS",
        help="classes the older peers come from (their trips only block the peers)",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        metavar="TOPIC",
        help="topics every group must cover, e.g. Reading Maths Media",
    )
    parser.add_argument(
        "--weeks",
        metavar="FROM-TO",
        help="ISO week range the calendar covers, e.g. 36-45",
    )
    parser.add_argument(
        "--app",
        action="store_true",
        help="serve the browser front end and print its address",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port for --app (default: a free one)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="with --app, do not open a browser window",
    )
    args = parser.parse_args(argv)

    if args.workbook is None:
        # The bundled exe is meant to be double clicked: with nothing named it opens
        # the front end. On the command line the example workbook is the friendly default.
        if getattr(sys, "frozen", False) and not (args.sample or args.new):
            args.app = True
        else:
            args.workbook = default_workbook()

    if args.app:
        from solver.app import serve

        return serve(port=args.port, open_browser=not args.no_browser)

    if args.new:
        try:
            spec = _spec_from_args(args)
        except ValueError as error:
            print(f"--new: {error}", file=sys.stderr)
            return 2
        path = write_scaffold(args.workbook, spec)
        groups = sum(splits for _cls, splits in spec.tutored)
        print(f"template workbook written to {path}")
        print(f"  {groups} group(s) from {len(spec.tutored)} class(es), "
              f"{len(spec.topics)} topic(s), weeks {spec.weeks[0]}-{spec.weeks[-1]}")
        print("  fill in the peer surnames and the trip marks, then run this tool on the file")
        return 0

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


def _spec_from_args(args) -> Spec:
    """Build a scaffold description from the --new options."""

    if not args.classes:
        raise ValueError("--new needs --classes, e.g. --classes 6a:2 6b:2")
    tutored = parse_classes(args.classes)
    topics = list(args.topics) if args.topics else ["Reading", "Maths", "Science", "Media"]
    weeks, dates = _week_range(args.weeks)
    return Spec(
        tutored=tutored,
        peer_classes=list(args.peer_classes or []),
        topics=topics,
        weeks=weeks,
        week_dates=dates,
    )


def _week_range(text: str | None) -> tuple[list[int], list[datetime.date] | None]:
    """The weeks to cover, and their Mondays.

    --weeks 36-45 gives week numbers only; without it the coming ten weeks are used
    and the calendar is headed with their Mondays, which also survives a year change.
    """

    if not text:
        dates = mondays(datetime.date.today(), TEN_WEEKS_AHEAD)
        return [date.isocalendar()[1] for date in dates], dates
    match = _RANGE.fullmatch(text.replace(" ", ""))
    if not match:
        raise ValueError(f"weeks should look like 36-45, not '{text}'")
    start, end = int(match.group(1)), int(match.group(2))
    if start > end:
        start, end = end, start
    if end - start > 52:
        raise ValueError("the week range may not cover more than a year")
    return list(range(start, end + 1)), None


_RANGE = re.compile(r"(\d{1,2})-(\d{1,2})")


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
