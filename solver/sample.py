"""A realistic example input workbook, so the sheet layout can be reviewed."""

from __future__ import annotations

from pathlib import Path

from solver.scaffold import Spec, write_scaffold

WEEKS = list(range(36, 46))

# The tutored classes: the groups are splits of these, and only their trips free a room.
TUTORED = ("6a", "6b", "6c")
# The classes the older peers come from: their trips only make peers unavailable.
PEER_CLASSES = ("9a", "9b", "10a", "10b", "11a")

TRIPS = {
    "6a": [36, 43],
    "6b": [37, 38, 44],
    "6c": [41, 45],
    "9a": [38, 41],
    "9b": [42, 45],
    "10a": [37],
    "10b": [44],
    "11a": [39, 43],
}

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


def spec() -> Spec:
    """The example semester as a scaffold description."""

    return Spec(
        tutored=[(cls, 2) for cls in TUTORED],
        peer_classes=list(PEER_CLASSES),
        topics=["Reading", "Maths", "Science", "Media"],
        weeks=WEEKS,
        trips=TRIPS,
        blackouts=[40],
        peer_cap=4,
        group_week_cap=2,
        peer_rows=PEERS,
    )


def write_sample_workbook(path: Path) -> Path:
    """The layout the planner expects, filled with an example semester."""

    return write_scaffold(path, spec())
