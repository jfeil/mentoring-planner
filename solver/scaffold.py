"""Builds an input workbook from a description, so nobody starts from an empty sheet.

Used by `main.py --new` and by the browser front end. The result is an ordinary
input workbook: Groups and Peers are filled in as far as the description goes and
the Calendar is a grid of blank cells to put their 'x' marks in.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")

README = [
    "How to use this workbook",
    "",
    "Groups: one row per class split, plus the class it belongs to. Already filled in.",
    "Peers: one row per group of older pupils that serves one topic. Their surnames are",
    "written in one cell, separated by ';', and 'Classes' lists their classes in the same",
    "order - 'Sander; Weise' with '9a; 9b' means Sander is in 9a and Weise is in 9b.",
    "  Available weeks - optional, e.g. '41-45' or '36, 38, 41'.",
    "  Max sessions    - optional, how often this peer group may be used at all.",
    "Calendar: rows are classes, columns are weeks; an x marks a class trip. Both the",
    "tutored classes and the peer classes are listed - please keep them, the planner",
    "reads both. The template starts with one example trip per tutored class, each in a",
    "different week, so it can be planned right away - replace them with the real ones.",
    "Settings: 'Max sessions per peer' is the default limit for peers that leave their",
    "own limit blank; 'Max sessions per group per week' caps how many sessions one class",
    "group may have in the same week (blank = no cap); 'Blackout weeks' are weeks with no",
    "mentoring at all (holidays, exam weeks, project weeks).",
    "",
    "The rules:",
    "  A room exists only in weeks where a TUTORED class is on a trip - a trip of a",
    "  peer's class does not open a room, it only makes that peer unavailable.",
    "  A group never meets in a week when its own class is away; a peer group never meets",
    "  in a week when any of its pupils' classes is away.",
    "  Every group does every topic exactly once, so it has one session per topic. A",
    "  week may hold several sessions for one group; the planner spreads them where it can.",
    "",
    "Fill in the peer surnames and the trips, then run the planner. The sheets Plan,",
    "Sessions, Loads, Overview and Notes are written for you.",
]


@dataclass
class Spec:
    """What to generate: classes, their splits, topics and the weeks in play."""

    tutored: list[tuple[str, int]]  # class name -> how many groups to split it into
    peer_classes: list[str]
    topics: list[str]
    weeks: list[int]
    peers_per_topic: int = 2
    trips: dict[str, list[int]] = field(default_factory=dict)
    blackouts: list[int] = field(default_factory=list)
    peer_cap: int | None = None
    group_week_cap: int | None = None
    peer_rows: list[tuple[str, str, str, str, str]] | None = None  # explicit Peers sheet
    week_dates: list[datetime.date] | None = None  # header cells instead of plain week numbers

    @property
    def week_labels(self) -> list:
        """Calendar header cells: the Mondays when they are known, else W36 style labels."""

        if self.week_dates:
            return list(self.week_dates)
        return [f"W{week}" for week in self.weeks]


def parse_classes(items: list[str]) -> list[tuple[str, int]]:
    """Read `--classes 6a:2 6b:3` into the pairs the scaffold wants."""

    parsed: list[tuple[str, int]] = []
    for item in items:
        name, _, splits = item.partition(":")
        name = name.strip()
        splits = splits.strip()
        if not name:
            raise ValueError(f"'{item}' names no class")
        if not splits:
            count = 1
        elif splits.isdigit() and int(splits) > 0:
            count = int(splits)
        else:
            raise ValueError(f"'{item}' needs a group count after ':', e.g. 6a:2")
        if any(name == existing for existing, _n in parsed):
            raise ValueError(f"class '{name}' is listed twice")
        parsed.append((name, count))
    return parsed


def group_names(spec: Spec) -> list[tuple[str, str]]:
    """The (group, class) rows the Groups sheet gets."""

    rows: list[tuple[str, str]] = []
    for cls, splits in spec.tutored:
        for number in range(1, splits + 1):
            rows.append((f"{cls}.{number}", cls))
    return rows


def weeks_from_dates(start: datetime.date, count: int) -> list[int]:
    """ISO week numbers of ``count`` consecutive Mondays, the first being ``start``."""

    return [monday.isocalendar()[1] for monday in mondays(start, count)]


def mondays(start: datetime.date, count: int) -> list[datetime.date]:
    """The ``count`` Mondays from the week of ``start`` onwards."""

    first_monday = start - datetime.timedelta(days=start.weekday())
    return [first_monday + datetime.timedelta(weeks=i) for i in range(count)]


def week_of(date: datetime.date) -> int:
    return date.isocalendar()[1]


def write_scaffold(path: Path, spec: Spec) -> Path:
    """Write the template workbook and return its path."""

    if not spec.tutored:
        raise ValueError("the scaffold needs at least one class to tutor")
    if not spec.topics:
        raise ValueError("the scaffold needs at least one topic")
    if not spec.weeks:
        raise ValueError("the scaffold needs at least one week")

    wb = Workbook()
    wb.remove(wb.active)

    groups = wb.create_sheet("Groups")
    _header(groups, ["Group", "Class"])
    for row in group_names(spec):
        groups.append(list(row))

    peers = wb.create_sheet("Peers")
    _header(peers, ["Peers (surnames)", "Topic", "Classes", "Available weeks", "Max sessions"])
    for row in spec.peer_rows if spec.peer_rows is not None else _blank_peers(spec):
        peers.append(list(row))

    trips = spec.trips or _example_trips(spec)

    calendar = wb.create_sheet("Calendar")
    _header(calendar, ["Class"] + list(spec.week_labels))
    for cls in [name for name, _splits in spec.tutored] + list(spec.peer_classes):
        marks = set(trips.get(cls, ()))
        calendar.append([cls] + ["x" if week in marks else "" for week in spec.weeks])

    settings = wb.create_sheet("Settings")
    _header(settings, ["Setting", "Value"])
    settings.append(["Max sessions per peer", spec.peer_cap if spec.peer_cap is not None else ""])
    settings.append(
        ["Max sessions per group per week", spec.group_week_cap if spec.group_week_cap is not None else ""]
    )
    settings.append(["Blackout weeks", ", ".join(str(w) for w in spec.blackouts)])

    readme = wb.create_sheet("Read me")
    for line in README:
        readme.append([line])
    readme["A1"].font = Font(bold=True)

    for ws in wb.worksheets:
        width = 18 if ws.title != "Read me" else 90
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = width
        ws.column_dimensions["A"].width = width
    wb.active = wb["Groups"]

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _example_trips(spec: Spec) -> dict[str, list[int]]:
    """One trip per tutored class, each in a different week.

    A template with no trip marks at all can never be planned - a room only exists
    in weeks where a tutored class travels - so the generated calendar starts with
    one mark per class and tells the reader to replace them.
    """

    trips: dict[str, list[int]] = {}
    for index, (cls, _splits) in enumerate(spec.tutored):
        trips[cls] = [spec.weeks[index % len(spec.weeks)]]
    return trips


def _blank_peers(spec: Spec) -> list[tuple[str, str, str, str, str]]:
    """Empty peer rows: the topics and classes are set, the surnames are not.

    Peer names have to be unique across the whole sheet, so the placeholder counts
    on through all topics instead of starting at one for each of them.
    """

    rows: list[tuple[str, str, str, str, str]] = []
    classes = spec.peer_classes or [cls for cls, _ in spec.tutored]
    number = 0
    for topic in spec.topics:
        for _ in range(max(spec.peers_per_topic, 1)):
            number += 1
            cls = classes[(number - 1) % len(classes)]
            rows.append((f"<peer {number}>", topic, cls, "", ""))
    return rows


def _header(ws, labels: list[str]) -> None:
    ws.append(labels)
    for col in range(1, len(labels) + 1):
        cell = ws.cell(1, col)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
