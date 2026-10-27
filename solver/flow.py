"""Max flow (Dinic) plus the lower-bound circulation trick.

The per-topic fairness problem is a bipartite b-matching: every group needs
exactly one peer and every peer should carry a similar number of groups. That
is exactly a flow problem once the peer->sink edges get a lower and an upper
bound, which we handle with the standard demand transformation.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, NamedTuple


class Edge(NamedTuple):
    u: int
    v: int
    lo: int
    hi: int


class Dinic:
    def __init__(self, n: int) -> None:
        self.n = n
        self.graph: list[list[list[int]]] = [[] for _ in range(n)]
        # graph[u] holds edges [to, cap, rev_index]; edge_ids maps added edges here.
        self._handles: list[tuple[int, int]] = []

    def add_edge(self, u: int, v: int, cap: int) -> int:
        self.graph[u].append([v, cap, len(self.graph[v])])
        self.graph[v].append([u, 0, len(self.graph[u]) - 1])
        self._handles.append((u, len(self.graph[u]) - 1))
        return len(self._handles) - 1

    def max_flow(self, s: int, t: int) -> int:
        total = 0
        while True:
            level = self._levels(s, t)
            if level[t] < 0:
                return total
            it = [0] * self.n
            while True:
                pushed = self._augment(s, t, float("inf"), level, it)
                if not pushed:
                    break
                total += pushed

    def flow(self, handle: int) -> int:
        u, idx = self._handles[handle]
        edge = self.graph[u][idx]
        return self.graph[edge[0]][edge[2]][1]

    def _levels(self, s: int, t: int) -> list[int]:
        level = [-1] * self.n
        level[s] = 0
        queue = deque([s])
        while queue:
            u = queue.popleft()
            for v, cap, _ in self.graph[u]:
                if cap > 0 and level[v] < 0:
                    level[v] = level[u] + 1
                    queue.append(v)
        return level

    def _augment(self, u: int, t: int, limit, level: list[int], it: list[int]) -> int:
        if u == t:
            return limit
        while it[u] < len(self.graph[u]):
            edge = self.graph[u][it[u]]
            v, cap, rev = edge
            if cap > 0 and level[v] == level[u] + 1:
                pushed = self._augment(v, t, min(limit, cap), level, it)
                if pushed:
                    edge[1] -= pushed
                    self.graph[v][rev][1] += pushed
                    return pushed
            it[u] += 1
        return 0


def feasible_circulation(n: int, edges: Iterable[Edge]) -> list[int] | None:
    """Find a flow satisfying every edge's [lo, hi]. Returns flows per edge.

    Nodes must form a circulation; for an s/t network add an edge t -> s with
    lo = 0 and hi = large, which is what the caller does.
    """

    edges = list(edges)
    net = [0] * n
    net_edges = []
    for u, v, lo, hi in edges:
        if lo > hi:
            return None
        net_edges.append((u, v, hi - lo))
        net[u] -= lo
        net[v] += lo

    source = n
    sink = n + 1
    dinic = Dinic(n + 2)
    handles = [dinic.add_edge(u, v, cap) for u, v, cap in net_edges]
    needed = 0
    for node, balance in enumerate(net):
        if balance > 0:
            dinic.add_edge(source, node, balance)
            needed += balance
        elif balance < 0:
            dinic.add_edge(node, sink, -balance)
    if dinic.max_flow(source, sink) != needed:
        return None
    return [dinic.flow(h) + edges[i].lo for i, h in enumerate(handles)]
