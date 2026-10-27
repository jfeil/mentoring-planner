"""The max-flow helpers: Dinic and the lower-bound circulation."""

from __future__ import annotations

import pytest

from solver.flow import Dinic, Edge, feasible_circulation


def test_a_simple_max_flow():
    dinic = Dinic(4)
    edges = [
        dinic.add_edge(0, 1, 3),
        dinic.add_edge(0, 2, 2),
        dinic.add_edge(1, 3, 2),
        dinic.add_edge(2, 3, 4),
    ]
    assert dinic.max_flow(0, 3) == 4  # 1 -> 3 can only carry 2, 0 -> 2 only 2
    assert [dinic.flow(h) for h in edges[:2]] == [2, 2]


def test_a_bottleneck_limits_the_flow():
    dinic = Dinic(3)
    dinic.add_edge(0, 1, 5)
    dinic.add_edge(1, 2, 2)
    assert dinic.max_flow(0, 2) == 2


def test_a_circulation_respects_the_bounds():
    # s -> a -> t with a minimum of one unit on the middle edge.
    edges = [Edge(2, 0, 1, 2), Edge(0, 1, 0, 2), Edge(1, 2, 1, 2)]
    flows = feasible_circulation(3, edges)
    assert flows is not None
    assert all(lo <= flow <= hi for flow, (_u, _v, lo, hi) in zip(flows, edges))
    assert flows[1] >= 1


def test_an_impossible_lower_bound_is_reported():
    # The middle edge can carry at most 1, but must carry at least 3.
    edges = [Edge(2, 0, 3, 3), Edge(0, 1, 0, 1), Edge(1, 2, 3, 3)]
    assert feasible_circulation(3, edges) is None


def test_lo_above_hi_is_rejected():
    assert feasible_circulation(2, [Edge(0, 1, 2, 1)]) is None


@pytest.mark.parametrize("capacity", [0, 1, 7])
def test_a_disconnected_sink_carries_nothing(capacity):
    dinic = Dinic(3)
    dinic.add_edge(0, 1, capacity)
    assert dinic.max_flow(0, 2) == 0
