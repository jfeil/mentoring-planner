"""A realistic example input workbook, so the sheet layout can be reviewed."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

WEEKS = list(range(36, 46))

# The tutored classes: the groups are splits of these, and only their trips free a room.
TUTORED = ("6a", "6b", "6c")
# The classes the older peers come from: their trips only make peers unavailable.
PEER_CLASSES = ("9a", "9b", "10a", "10b", "11a")

TRIPS = {
    "6a": {36, 43},
    "6b": {37, 38, 44},
    "6c": {41, 45},
    "9a": {38, 41},
    "9b": {42, 45},
    "10a": {37},
    "10b": {44},
    "11a": {39, 43},
}

GROUPS = [
    ("6a.1", "6a"),
    ("6a.2", "6a"),
    ("6b.1", "6b"),
    ("6b.2", "6b"),
    ("6c.1", "6c"),
    ("6c.2", "6c"),
]

# A peer is a fixed group of older pupils: surnames separated by ';', classes in the same order.
PEERS = [
    ("Sander; Weise", "Reading", "9a; 9b", "", ""),
    ("Bergmann", "Reading", "10b", "", ""),
    ("Fichtner; Tolles", "Reading", "10a; 10b", "", ""),
    ("Reuter; Starck", "Maths", "9b; 11a", "", ""),
    ("Pandur", "Maths", "10b", "", ""),
    ("Beckmann; Simon", "Maths", "11a; 9a", "", ""),
    ("Starck; Weise", "Science", "11a; 9b", "", ""),
    ("Tolles", "Science", "10a", "", ""),
    ("Simon; Sander", "Science", "9a", "", ""),
    ("Simon; Pandur", "Media", "9a; 10b", "", "2"),
    ("Beckmann", "Science", "11a", "", ""),
    ("Weise; Bergmann", "Media", "9b; 10b", "36-43", ""),
]

HEADERS = {
    "Groups": ["Group", "Class"],
    "Peers": ["Peers (surnames)", "Topic", "Classes", "Available weeks", "Max sessions"],
    "Calendar": ["Class"] + [f"W{w}" for w in WEEKS],
    "Settings": ["Setting", "Value"],
}

SETTINGS = [
    ("Max sessions per peer", "4"),
    ("Max sessions per group per week", "2"),
    ("Blackout weeks", "40"),
]

README = [
    "How to use this workbook",
    "",
    "Groups: one row per class split, plus the class it belongs to.",
    "Peers: one row per group of older pupils that serves one topic. Their surnames are",
    "written in one cell, separated by ';', and 'Classes' lists their classes in the same",
    "order - 'Sander; Weise' with '9a; 9b' means Sander is in 9a and Weise is in 9b.",
    "  Available weeks - optional, e.g. '41-45' or '36, 38, 41'.",
    "  Max sessions    - optional, how often this peer group may be used at all.",
    "Calendar: rows are classes, columns are weeks; an x marks a class trip. Please list",
    "both the tutored classes and the classes the peers come from.",
    "Settings: optional. 'Max sessions per peer' is the default limit for peers that",
    "leave their own limit blank; 'Max sessions per group per week' caps how many",
    "sessions one class group may have in the same week (blank = no cap); 'Blackout",
    "weeks' are weeks with no mentoring at all (holidays, exam weeks, project weeks).",
    "",
    "The rules:",
    "  A room exists only in weeks where a TUTORED class is on a trip - a trip of a",
    "  peer's class does not open a room, it only makes that peer unavailable.",
    "  A group never meets in a week when its own class is away; a peer group never meets",
    "  in a week when any of its pupils' classes is away.",
    "  Every group does every topic exactly once, so it has one session per topic. A",
    "  week may hold several sessions for one group; the planner spreads them where it can.",
    "",
    "Run: uv run python main.py example/input.xlsx",
    "The sheets Plan, Sessions, Loads, Overview and Notes are written for you.",
]


def write_sample_workbook(path: Path) -> Path:
    """The layout the planner expects, filled with an example semester."""

    wb = Workbook()
    wb.remove(wb.active)

    groups = wb.create_sheet("Groups")
    _header(groups, HEADERS["Groups"])
    for row in GROUPS:
        groups.append(list(row))

    peers = wb.create_sheet("Peers")
    _header(peers, HEADERS["Peers"])
    for row in PEERS:
        peers.append(list(row))

    calendar = wb.create_sheet("Calendar")
    _header(calendar, HEADERS["Calendar"])
    for cls in TUTORED + PEER_CLASSES:
        calendar.append([cls] + ["x" if week in TRIPS[cls] else "" for week in WEEKS])

    settings = wb.create_sheet("Settings")
    _header(settings, HEADERS["Settings"])
    for row in SETTINGS:
        settings.append(list(row))

    readme = wb.create_sheet("Read me")
    for line in README:
        readme.append([line])
    readme["A1"].font = Font(bold=True)

    for ws in wb.worksheets:
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 13 if ws.title != "Peers" else 18
        ws.column_dimensions["A"].width = 90 if ws.title == "Read me" else 18
    wb.active = wb["Groups"]
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _header(ws, labels: list[str]) -> None:
    ws.append(labels)
    for col in range(1, len(labels) + 1):
        cell = ws.cell(1, col)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E2F3")
