"""Choosing the weeks: the spread, and the 'Max sessions per group per week' limit."""

from __future__ import annotations

import collections

from helpers import write_workbook

from solver import load_workbook, solve


def planned(tmp_path, cap: int, blackouts=()):
    settings = [
        ("Max sessions per peer", "4"),
        ("Max sessions per group per week", str(cap)),
    ]
    if blackouts:
        settings.append(("Blackout weeks", ", ".join(map(str, blackouts))))
    data = load_workbook(write_workbook(tmp_path / f"cap{cap}.xlsx", settings=settings))
    return data, solve(data)


def week_counts(group) -> collections.Counter:
    return collections.Counter(session.week for session in group.assigned)


def test_the_setting_is_read(tmp_path):
    data, _plan = planned(tmp_path, 2)
    assert data.group_week_cap == 2


def test_without_the_setting_a_group_may_stack_a_week(data, plan):
    assert data.group_week_cap is None
    # 6a.2 can only use W36 and W39 for three of its sessions, so one week is doubled.
    stacked = [group for group in data.groups if max(week_counts(group).values(), default=0) > 1]
    assert [group.name for group in stacked] == ["6a.2"]


def test_a_group_is_spread_over_as_many_weeks_as_it_can(data, plan):
    """Nobody stacks a week that could still have been avoided."""

    for group in data.groups:
        counts = week_counts(group)
        usable = {
            week
            for session in group.assigned
            for week in data.allowed_weeks(group, session.peer)
        }
        busiest = max(counts.values())
        assert busiest >= -(-len(group.assigned) // len(usable)), f"{group.name}: {counts}"


def test_the_limit_is_never_exceeded(tmp_path):
    data, plan = planned(tmp_path, 1)
    for group in data.groups:
        assert max(week_counts(group).values(), default=0) <= 1


def test_two_per_week_is_enough_for_the_example(tmp_path):
    _data, plan = planned(tmp_path, 2)
    assert plan.complete
    assert len(plan.sessions) == 12


def test_a_limit_that_cannot_be_met_leaves_a_note(tmp_path):
    # Blocking W34 and W36 leaves class 6b with only W38, which cannot hold three sessions.
    data, plan = planned(tmp_path, 1, blackouts=(34, 36))
    group = next(g for g in data.groups if g.name == "6b.1")
    assert max(week_counts(group).values()) == 1
    missing = [topic for name, topic in plan.unresolved if name == "6b.1"]
    assert len(missing) == 2
    assert any("Max sessions per group per week" in note for note in plan.notes)
