"""Balanced per-topic assignment of peers to groups.

Each group visits each topic exactly once, so every topic is one bipartite
matching problem: the groups on one side, the peers of that topic on the other,
and an edge only where some open week works for both sides -- a group is out in
a week when its own class travels, and a peer is out in a week when any class of
its member pupils travels. Fairness is solved exactly rather than greedily:
first the busiest peer is made as free as possible, then the idlest peer as busy
as possible, honouring the per-peer 'Max sessions' column.

Weeks are chosen in a second pass. They are not a capacity limit - a group may
well have two sessions in one week, and the workbook can cap that with 'Max
sessions per group per week' - so for each group we match its sessions to weeks
again, this time keeping its busiest week as empty as possible. Every session
also lists the peers and weeks that would work instead, for manual swapping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from solver.flow import Dinic, Edge, feasible_circulation
from solver.model import Assignment, Data, Group, Peer


class UnfeasibleError(Exception):
    """Nothing at all could be planned; the workbook needs different input."""


@dataclass
class Plan:
    data: Data
    sessions: list[Assignment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unresolved: list[tuple[str, str]] = field(default_factory=list)  # (group, topic)

    @property
    def complete(self) -> bool:
        return not self.unresolved

    def peer_loads(self) -> dict[str, int]:
        loads = {p.name: 0 for p in self.data.peers}
        for s in self.sessions:
            loads[s.peer.name] += 1
        return loads

    def week_loads(self) -> dict[int, int]:
        loads: dict[int, int] = {}
        for s in self.sessions:
            loads[s.week] = loads.get(s.week, 0) + 1
        return loads

    def spread(self, topic: str) -> tuple[int, int]:
        """(idlest, busiest) session count among the peers of a topic."""

        loads = [self.peer_loads()[p.name] for p in self.data.peers_for(topic)]
        return (min(loads), max(loads)) if loads else (0, 0)

    def week_options(self, session: Assignment) -> tuple[int, ...]:
        """Weeks this peer could be moved to for this group."""

        return self.data.weeks_left_for(session.group, session.peer, self._group_weeks(session))

    def alternatives(self, session: Assignment, limit: int = 3) -> list[tuple[Peer, tuple[int, ...]]]:
        """Other peers for this group and topic, free week(s) each.

        Peers with spare capacity come first, so a sick peer can be replaced
        without unbalancing the loads.
        """

        loads = self.peer_loads()
        used = self._group_weeks(session)
        options = []
        for peer in self.data.peers_for(session.peer.topic):
            if peer is session.peer:
                continue
            weeks = self.data.weeks_left_for(session.group, peer, used)
            if not weeks:
                continue
            cap = self.data.cap_of(peer)
            spare = float("inf") if cap is None else cap - loads[peer.name]
            options.append((spare, loads[peer.name], peer.name, peer, weeks))
        options.sort()
        return [(peer, weeks) for _spare, _load, _name, peer, weeks in options[:limit]]

    def _group_weeks(self, session: Assignment) -> dict[int, int]:
        """Week loads of this group, ignoring the session that would move away."""

        loads: dict[int, int] = {}
        for other in session.group.assigned:
            if other is not session:
                loads[other.week] = loads.get(other.week, 0) + 1
        return loads

    def option_count(self, session: Assignment) -> int:
        used = self._group_weeks(session)
        return sum(
            1
            for peer in self.data.peers_for(session.peer.topic)
            if peer is not session.peer and self.data.weeks_left_for(session.group, peer, used)
        )


def solve(data: Data) -> Plan:
    """One session per (group, topic) where the calendar allows it."""

    plan = Plan(data=data)
    _report_weeks(data, plan)
    matches: list[tuple[Group, Peer]] = []
    for topic in data.topics:
        matches.extend(_solve_topic(data, topic, plan))
    _place_weeks(data, plan, matches)

    plan.sessions.sort(key=lambda s: (s.week, s.group.name, s.peer.topic))
    if data.groups and data.topics and not plan.sessions:
        raise UnfeasibleError(
            "no session could be placed: no group has a peer it could meet in an open week"
        )
    return plan


def _report_weeks(data: Data, plan: Plan) -> None:
    open_weeks = data.open_weeks
    if not open_weeks:
        plan.notes.append("the calendar leaves no usable week: no class trip, or every week is blocked")
        return
    closed = [w for w in data.weeks if not data.is_open(w)]
    if closed:
        reasons = ", ".join(
            f"W{w} ({'blocked' if w in data.blackouts else 'no class travels'})" for w in closed
        )
        plan.notes.append(f"no mentoring in: {reasons}")
    plan.notes.append("room available in week(s) " + ", ".join(str(w) for w in open_weeks))


def _solve_topic(data: Data, topic: str, plan: Plan) -> list[tuple[Group, Peer]]:
    """Which peer serves which group for one topic; the week is chosen later."""

    peers = data.peers_for(topic)
    if not peers:
        plan.unresolved.extend((g.name, topic) for g in data.groups)
        plan.notes.append(f"topic '{topic}' has no peers, so no group can visit it")
        return []

    weeks = {(g, p): data.allowed_weeks(g, p) for g in data.groups for p in peers}
    pairs = [(g, p) for (g, p), w in weeks.items() if w]

    groups = [g for g in data.groups if any(gg is g for gg, _p in pairs)]
    active = [p for p in peers if any(p is pp for _g, pp in pairs)]
    for group in data.groups:
        if group not in groups:
            plan.unresolved.append((group.name, topic))
            plan.notes.append(
                f"group '{group.name}' (class {group.cls}) cannot reach topic '{topic}': "
                "no peer of that topic shares an open week with it"
            )
    for peer in peers:
        if peer not in active:
            plan.notes.append(f"peer '{peer.name}' (topic '{topic}') fits no group in any open week")
    if not groups:
        return []

    caps = [min(data.cap_of(p) or len(groups), len(groups)) for p in active]
    capped = [p.name for p, cap in zip(active, caps) if data.cap_of(p) is not None]
    index_group = {id(g): i for i, g in enumerate(groups)}
    index_peer = {id(p): j for j, p in enumerate(active)}
    edges = [(index_group[id(g)], index_peer[id(p)]) for g, p in pairs]

    wanted = len(groups)
    if sum(caps) < wanted:
        wanted = _max_sessions(len(groups), len(active), edges, caps)
        plan.notes.append(
            f"topic '{topic}': the session limits only allow {wanted} of {len(groups)} sessions"
            f" (limited peers: {', '.join(capped) or 'none'}); raise 'Max sessions' to fit the rest"
        )

    lows, used_caps = _balance(wanted, len(groups), caps, edges)
    matched = _assignment(len(groups), len(active), edges, lows, used_caps, sessions=wanted)
    if matched is None:  # keep a plan rather than crash; normally unreachable
        matched = _assignment(len(groups), len(active), edges, [0] * len(active), caps, sessions=wanted)
        if matched is None:
            matched = {}
        plan.notes.append(f"topic '{topic}': the balances could not all be met, loads may differ")

    for peer_index, peer in enumerate(active):
        if caps[peer_index] == 0:
            plan.notes.append(f"peer '{peer.name}' (topic '{topic}') is capped at 0 sessions")

    matches: list[tuple[Group, Peer]] = []
    loads = [0] * len(active)
    for i, group in enumerate(groups):
        if i not in matched:
            plan.unresolved.append((group.name, topic))
            continue
        peer = active[matched[i]]
        loads[matched[i]] += 1
        matches.append((group, peer))

    extra = "" if sum(caps) >= len(groups) else f", limits allow at most {sum(caps)}"
    plan.notes.append(
        f"topic '{topic}': {len(matches)} session(s) over {len(active)} peer(s), "
        f"loads {min(loads) if loads else 0}-{max(loads) if loads else 0}{extra}"
    )
    return matches


def _balance(
    n_sessions: int, n_groups: int, caps: list[int], edges: list[tuple[int, int]]
) -> tuple[list[int], list[int]]:
    """Target loads: minimise the busiest peer, then maximise the idlest, within the caps."""

    n_peers = len(caps)
    lo, hi = math.ceil(n_sessions / n_peers), max(caps)
    while lo < hi:
        mid = (lo + hi) // 2
        bounds = [min(cap, mid) for cap in caps]
        placed = _assignment(n_groups, n_peers, edges, [0] * n_peers, bounds, sessions=n_sessions)
        if placed is not None:
            hi = mid
        else:
            lo = mid + 1
    ceiling = [min(cap, lo) for cap in caps]

    low, high = 0, min(max(ceiling), n_sessions // n_peers)
    while low < high:
        mid = (low + high + 1) // 2
        floor_bounds = [min(cap, mid) for cap in ceiling]
        placed = _assignment(n_groups, n_peers, edges, floor_bounds, ceiling, sessions=n_sessions)
        if placed is not None:
            low = mid
        else:
            high = mid - 1
    return [min(cap, low) for cap in ceiling], ceiling


def _max_sessions(n_groups: int, n_peers: int, edges: list[tuple[int, int]], caps: list[int]) -> int:
    """How many sessions fit at all when the caps are too tight."""

    for sessions in range(min(n_groups, sum(caps)), 0, -1):
        if _assignment(n_groups, n_peers, edges, [0] * n_peers, caps, sessions=sessions) is not None:
            return sessions
    return 0


def _assignment(
    n_groups: int,
    n_peers: int,
    edges: list[tuple[int, int]],
    lows: list[int],
    caps: list[int],
    sessions: int | None = None,
) -> dict[int, int] | None:
    """Match groups to peers within the load bounds; returns group index -> peer index."""

    sessions = n_groups if sessions is None else sessions
    if not 0 <= sessions <= n_groups or sum(lows) > sessions or sum(caps) < sessions:
        return None
    source, sink = n_groups + n_peers, n_groups + n_peers + 1
    flow_edges = [Edge(sink, source, sessions, sessions)]
    for i in range(n_groups):
        flow_edges.append(Edge(source, i, 1 if sessions == n_groups else 0, 1))
    for j in range(n_peers):
        flow_edges.append(Edge(n_groups + j, sink, lows[j], caps[j]))
    first_pair_edge = len(flow_edges)
    for gi, pj in edges:
        flow_edges.append(Edge(gi, n_groups + pj, 0, 1))

    flows = feasible_circulation(sink + 1, flow_edges)
    if flows is None:
        return None
    matched: dict[int, int] = {}
    for k, (gi, pj) in enumerate(edges):
        if flows[first_pair_edge + k] > 0:
            matched[gi] = pj
    return matched if len(matched) == sessions else None


def _pick_week(weeks: tuple[int, ...], group: Group, peer: Peer, plan: Plan) -> int:
    """Prefer a week where neither this group nor this peer meets yet."""

    used = {s.week for s in group.assigned} | {s.week for s in peer.assigned}
    load = plan.week_loads()
    return min(weeks, key=lambda w: (w in used, load.get(w, 0), w))


def _place_weeks(data: Data, plan: Plan, matches: list[tuple[Group, Peer]]) -> None:
    """Give every session a week.

    Weeks do not compete for capacity - any number of sessions can run in the same
    week - so the only real question is which weeks a group can use at all. The
    planner spreads a group's sessions over as many different weeks as the calendar
    allows, never above 'Max sessions per group per week'.
    """

    by_group: dict[Group, list[tuple[Peer, tuple[int, ...]]]] = {}
    for group, peer in matches:
        by_group.setdefault(group, []).append((peer, data.allowed_weeks(group, peer)))

    for group in data.groups:
        rows = by_group.get(group)
        if not rows:
            continue
        cap = data.group_week_cap if data.group_week_cap is not None else len(rows)
        keep = len(rows)
        chosen = _spread_weeks([weeks for _peer, weeks in rows], cap)
        while chosen is None and keep > 1:  # the limit is too tight: keep what fits
            keep -= 1
            chosen = _spread_weeks([weeks for _peer, weeks in rows[:keep]], cap)
        if chosen is None:
            for peer, _weeks in rows:
                plan.unresolved.append((group.name, peer.topic))
            plan.notes.append(
                f"group '{group.name}': no week is free for it at its limit of "
                f"{cap} session(s) per week"
            )
            continue
        if keep < len(rows):
            for peer, _weeks in rows[keep:]:
                plan.unresolved.append((group.name, peer.topic))
            plan.notes.append(
                f"group '{group.name}': only {keep} of {len(rows)} session(s) fit at {cap} per "
                f"week; {', '.join(peer.topic for peer, _w in rows[keep:])} left unplanned - "
                "raise 'Max sessions per group per week' to fit them"
            )
        for (peer, _weeks), week in zip(rows, chosen):
            session = Assignment(group=group, peer=peer, week=week)
            group.assigned.append(session)
            peer.assigned.append(session)
            plan.sessions.append(session)


def _spread_weeks(allowed: list[tuple[int, ...]], cap: int) -> list[int] | None:
    """One week per session, at most ``cap`` in one week, over as many weeks as possible."""

    options = [list(weeks) for weeks in allowed]
    if any(not weeks for weeks in options):
        return None
    weeks = sorted({w for choices in options for w in choices})
    if len(weeks) * cap < len(options):
        return None

    lo, hi = 1, min(cap, len(options))
    while lo < hi:  # the least busy week can still be made busier
        mid = (lo + hi) // 2
        if _week_flow(options, weeks, mid) is not None:
            hi = mid
        else:
            lo = mid + 1
    return _week_flow(options, weeks, lo)


def _week_flow(options: list[list[int]], weeks: list[int], cap: int) -> list[int] | None:
    """Assign every session a week, at most ``cap`` per week; max flow decides it."""

    n, m = len(options), len(weeks)
    column = {w: j for j, w in enumerate(weeks)}
    source, sink = 0, n + m + 1
    dinic = Dinic(sink + 1)
    for i in range(n):
        dinic.add_edge(source, 1 + i, 1)
    handles: list[tuple[int, int, int]] = []  # (session, week, edge handle)
    for i, choices in enumerate(options):
        for w in choices:
            handles.append((i, w, dinic.add_edge(1 + i, 1 + n + column[w], 1)))
    for j in range(m):
        dinic.add_edge(1 + n + j, sink, cap)
    if dinic.max_flow(source, sink) != n:
        return None

    chosen: list[int] = [-1] * n
    for i, w, handle in handles:
        if dinic.flow(handle) > 0:
            chosen[i] = w
    return chosen if all(w >= 0 for w in chosen) else None
