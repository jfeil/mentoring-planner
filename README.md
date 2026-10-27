# Mentoring planner

Assigns mentoring sessions for a school project: fixed groups of older pupils (*peers*,
given by surname) meet small groups that a class has been split into (`6a.1`, `6b.3`, ...),
one hour each, **once per group per topic**. Input and output are one Excel workbook, so the
sheet stays the place where the plan is kept and edited.

The planner solves the fairness part exactly (max-flow with lower bounds): per topic it
balances how often each peer group is used, then it picks weeks so that no group has all of
its sessions crammed into one week, within the limits set in the workbook.

## Running it

Double click `mentoring-planner.exe` (see [releases](../../releases)) and a small page opens:
upload a workbook and get it back planned, or create a new one - classes, split counts,
topics, a date for the first week, and a grid to tick the class trips in.

From a shell:

```
uv run python main.py                     # write example/input.xlsx and plan it
uv run python main.py path/to/input.xlsx  # plan your own workbook
uv run python main.py input.xlsx --out plan.xlsx
uv run python main.py --new template.xlsx --classes 6a:2 6b:2 --peer-classes 9a 9b \
    --topics Reading Maths --weeks 36-45   # an empty workbook to fill in
uv run python main.py --app                # the browser front end, on localhost
```

Exit codes: `0` planned, `1` some session could not be placed, `2` the workbook was unreadable.

## The workbook

| Sheet | What goes in it |
| --- | --- |
| `Groups` | `Group` \| `Class` - the class splits to tutor |
| `Peers` | `Peers (surnames)` \| `Topic` \| `Classes` \| `Available weeks` \| `Max sessions` |
| `Calendar` | one row per class, one column per week; an `x` marks a class trip |
| `Settings` | optional: `Max sessions per peer`, `Max sessions per group per week`, `Blackout weeks` |

A peer entry is a whole group of pupils: `Sander; Weise` with `9a; 9b` means Sander is in 9a
and Weise in 9b. `Peers` rows may be written in German (`Betreuer | Thema | Klassen`), and the
`Calendar` columns may be headed with week numbers (`36`, `W36`, `KW36`) or with the Mondays.

The planner writes `Plan`, `Sessions`, `Loads`, `Overview` and `Notes` and replaces them on
every run. `Sessions` also lists, for every session, the weeks and the other peer groups that
would have been possible - so swapping someone out who is sick is a matter of reading across.

## The rules, in one place

* A room exists **only** in weeks where a *tutored* class is on a trip. A peer's class trip
  does not open a room, it only makes that peer unavailable.
* A group never meets in a week its own class is away; a peer group never meets in a week any
  of its pupils' classes is away.
* Every group does every topic exactly once. Several sessions per week per group are allowed;
  `Max sessions per group per week` caps that, and the planner spreads them where it can.
* Blackout weeks (holidays, exam weeks) carry nothing at all.

Because the room only exists while a tutored class travels, a workbook whose groups all come
from one class can never be planned - the planner says so instead of returning an empty plan.

## Tests

```
uv sync
uv run pytest
```

`tests/fixtures/input.xlsx` plus `expected.json` are the golden example: 12 sessions, planned
and compared session by session. Regenerate them with `uv run python -m tests.make_fixture`.

## Building the executable

```
uv run pyinstaller --clean mentoring-planner.spec   # -> dist/mentoring-planner(.exe)
```

GitHub Actions (`.github/workflows/ci.yml`) runs the tests on every push and pull request,
builds the Windows and Linux executables on every push to `main` as artifacts, and attaches
them to a GitHub release when a `v*` tag is pushed.
