"""What the planner guarantees, plus the golden plan for the example workbook."""

from __future__ import annotations

import collections

from helpers import EXPECTED, read_expected, write_workbook

from solver import load_workbook, solve


# --- the fixed requirement: every group, every topic, exactly once ---------------

def test_every_group_gets_every_topic(data, plan):
    pairs = {(s.group.name, s.peer.topic) for s in plan.sessions}
    expected = {(g.name, t) for g in data.groups for t in data.topics}
    assert pairs == expected


def test_no_group_or_topic_is_scheduled_twice(data, plan):
    counts = collections.Counter((s.group.name, s.peer.topic) for s in plan.sessions)
    assert [pair for pair, n in counts.items() if n != 1] == []
    assert len(plan.sessions) == len(data.groups) * len(data.topics)
    assert plan.unresolved == []


# --- availability ---------------------------------------------------------------

def test_sessions_only_land_in_open_weeks(data, plan):
    open_weeks = set(data.open_weeks)
    assert all(s.week in open_weeks for s in plan.sessions)


def test_no_session_conflicts_with_a_trip(data, plan):
    for s in plan.sessions:
        assert s.week not in data.trips.get(s.group.cls, set()), f"{s.group.name} trip in W{s.week}"
        assert s.week not in s.peer.trip_weeks(data.trips), f"{s.peer.name} trip in W{s.week}"


def test_a_peer_class_trip_never_opens_a_week(data, plan):
    # W37 (9a away) and W40 (11a away) have no tutored trip, so no room exists there.
    assert all(s.week not in (37, 40) for s in plan.sessions)


# --- session limits -------------------------------------------------------------

def test_peer_limits_are_respected(data, plan):
    loads = plan.peer_loads()
    for peer in data.peers:
        cap = data.cap_of(peer)
        if cap is not None:
            assert loads[peer.name] <= cap, f"{peer.name}: {loads[peer.name]} > {cap}"


def test_a_limit_of_one_is_not_exceeded(tmp_path):
    peers = [
        ("Sander; Weise", "Reading", "9a; 10a", "", "1"),
        ("Bergmann", "Reading", "11a", "", "1"),
    ]
    data = load_workbook(
        write_workbook(tmp_path / "capped.xlsx", peers=peers, settings=[("Max sessions per peer", "1")])
    )
    plan = solve(data)
    assert set(plan.peer_loads().values()) == {1}
    assert len(plan.sessions) == 2  # three groups, but only two single-session peers
    assert [g for g, topic in plan.unresolved] and all(t == "Reading" for _g, t in plan.unresolved)
    assert any("session limits" in note for note in plan.notes)


def test_balancing_respects_the_limits(tmp_path):
    # One peer may work only once, so an even split is impossible and the others absorb it.
    peers = [
        ("Simon", "Media", "9a", "", "1"),
        ("Weise", "Media", "10a", "", ""),
        ("Pandur", "Media", "11a", "", ""),
    ]
    data = load_workbook(write_workbook(tmp_path / "lopsided.xlsx", peers=peers, settings=None))
    plan = solve(data)
    loads = plan.peer_loads()
    assert loads["Simon"] == 1  # its limit
    assert max(loads.values()) - min(loads.values()) <= 1  # the rest stayed even


# --- fairness -------------------------------------------------------------------

def test_topic_loads_are_as_even_as_the_limits_allow(data, plan):
    """The busiest peer of a topic carries the smallest load that the limits allow."""

    loads = plan.peer_loads()
    for topic in data.topics:
        peers = data.peers_for(topic)
        caps = [data.cap_of(p) or 10**6 for p in peers]
        sessions = sum(loads[p.name] for p in peers)
        best = next(
            k for k in range(1, sessions + 1) if sum(min(cap, k) for cap in caps) >= sessions
        )
        assert max(loads[p.name] for p in peers) == best, f"{topic}: {loads}"


def test_a_tighter_limit_is_spread_over_the_free_peers(tmp_path):
    peers = [
        ("Simon", "Media", "9a", "", "2"),
        ("Weise", "Media", "10a", "", ""),
        ("Pandur", "Media", "11a", "", ""),
    ]
    data = load_workbook(
        write_workbook(tmp_path / "spread.xlsx", peers=peers, settings=[("Max sessions per peer", "3")])
    )
    plan = solve(data)
    loads = plan.peer_loads()
    assert loads["Simon"] <= 2
    assert max(loads.values()) - min(loads.values()) <= 1


# --- alternatives ---------------------------------------------------------------

def test_alternatives_are_usable_swaps(data, plan):
    checked = 0
    for session in plan.sessions:
        for peer, weeks in plan.alternatives(session):
            assert peer.topic == session.peer.topic
            assert session.group.name not in [s.group.name for s in peer.assigned]
            assert any(w in data.allowed_weeks(session.group, peer) for w in weeks)
            checked += 1
    assert checked > 0


# --- golden output for the example workbook -------------------------------------

def test_example_workbook_matches_the_expected_plan(committed_fixture):
    from helpers import plan_rows

    plan = solve(load_workbook(committed_fixture))
    assert plan_rows(plan) == read_expected(EXPECTED)["sessions"]


def test_solving_is_deterministic(data):
    from helpers import plan_rows

    assert plan_rows(solve(data)) == plan_rows(solve(data))
