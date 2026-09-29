"""Split a catchment's lanes into fair, contiguous, non-overlapping chunks of survey work.

Fair       -> chunks have similar walking *effort* (lane length, busier roads weighted up).
Contiguous -> each chunk is grown along the street graph from a seed, so a surveyor walks a
              connected patch instead of criss-crossing the catchment.
Non-overlapping -> it is a partition: every lane lands in exactly one chunk.

Algorithm: farthest-point seeds, then balanced region growing (always extend the currently
lightest chunk with its nearest adjacent unassigned lane), then attach disconnected leftovers
to the nearest chunk, then a boundary-rebalancing pass.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

TARGET_EFFORT_M = 3000.0  # about one surveyor-session of lanes
BUSY_ROAD_FACTOR = 1.5    # busier roads take longer (traffic, more shops per metre)
BUSY = {"tertiary", "unclassified"}


@dataclass(frozen=True)
class Lane:
    id: str
    length_m: float
    highway: str
    start_node: int
    end_node: int
    x: float  # midpoint in local metres
    y: float

    @property
    def effort(self) -> float:
        return self.length_m * (BUSY_ROAD_FACTOR if self.highway in BUSY else 1.0)


def to_local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    return ((lon - lon0) * 111_320 * math.cos(math.radians(lat0)), (lat - lat0) * 110_540)


def _node_roots(connectors: list[tuple[int, int]]) -> dict[int, int]:
    """Union-find over connector segments (main roads nobody surveys door to door): every node
    along one arterial collapses into one super-node, so lanes on either side stay neighbours."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in connectors:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return {n: find(n) for n in parent}


def adjacency(lanes: list[Lane], connectors: list[tuple[int, int]] = ()) -> dict[str, set[str]]:
    root = _node_roots(list(connectors))
    by_node: dict[int, list[str]] = defaultdict(list)
    for ln in lanes:
        by_node[root.get(ln.start_node, ln.start_node)].append(ln.id)
        by_node[root.get(ln.end_node, ln.end_node)].append(ln.id)
    adj: dict[str, set[str]] = {ln.id: set() for ln in lanes}
    for ids in by_node.values():
        for a in ids:
            adj[a].update(i for i in ids if i != a)
    return adj


def _farthest_point_seeds(lanes: list[Lane], k: int) -> list[Lane]:
    # Start from the lane farthest from the centroid, then repeatedly add the farthest lane.
    cx = sum(ln.x for ln in lanes) / len(lanes)
    cy = sum(ln.y for ln in lanes) / len(lanes)
    seeds = [max(lanes, key=lambda ln: (ln.x - cx) ** 2 + (ln.y - cy) ** 2)]
    dist = {ln.id: (ln.x - seeds[0].x) ** 2 + (ln.y - seeds[0].y) ** 2 for ln in lanes}
    while len(seeds) < k:
        nxt = max(lanes, key=lambda ln: dist[ln.id])
        seeds.append(nxt)
        for ln in lanes:
            dist[ln.id] = min(dist[ln.id], (ln.x - nxt.x) ** 2 + (ln.y - nxt.y) ** 2)
    return seeds


def split(lanes: list[Lane], target_effort_m: float = TARGET_EFFORT_M, max_chunks: int = 12,
          connectors: list[tuple[int, int]] = ()) -> list[list[str]]:
    """Returns chunks as lists of lane ids (partition of the input). `connectors` are the
    (start, end) nodes of non-surveyed road segments that join lanes together."""
    if not lanes:
        return []
    total = sum(ln.effort for ln in lanes)
    k = max(1, min(max_chunks, len(lanes), round(total / target_effort_m)))
    if k == 1:
        return [[ln.id for ln in lanes]]
    by_id = {ln.id: ln for ln in lanes}
    adj = adjacency(lanes, connectors)
    seeds = _farthest_point_seeds(lanes, k)

    owner: dict[str, int] = {}
    members: list[set[str]] = []
    effort = [0.0] * k
    for i, s in enumerate(seeds):
        owner[s.id] = i
        members.append({s.id})
        effort[i] = s.effort
    frontier: list[set[str]] = [set(adj[s.id]) - set(owner) for s in seeds]
    blocked: set[int] = set()

    while len(owner) < len(lanes) and len(blocked) < k:
        i = min((j for j in range(k) if j not in blocked), key=lambda j: effort[j])
        frontier[i] -= set(owner)
        if not frontier[i]:
            blocked.add(i)
            continue
        sx, sy = seeds[i].x, seeds[i].y
        pick = min(frontier[i], key=lambda lid: (by_id[lid].x - sx) ** 2 + (by_id[lid].y - sy) ** 2)
        owner[pick] = i
        members[i].add(pick)
        effort[i] += by_id[pick].effort
        frontier[i] |= adj[pick] - set(owner)

    # Disconnected leftovers (islands in the street graph): nearest chunk by seed distance.
    for ln in lanes:
        if ln.id not in owner:
            i = min(range(k), key=lambda j: (ln.x - seeds[j].x) ** 2 + (ln.y - seeds[j].y) ** 2)
            owner[ln.id] = i
            members[i].add(ln.id)
            effort[i] += ln.effort

    _rebalance(members, effort, owner, adj, by_id)
    _merge_small(members, effort, owner, adj, by_id, seeds)
    return [sorted(m) for m in members if m]


def _merge_small(members, effort, owner, adj, by_id, seeds, min_share: float = 0.55) -> None:
    """Chunks hemmed in by their neighbours can end up tiny. Fold any chunk below
    `min_share` of the mean effort into its lightest neighbouring chunk (or the nearest)."""
    while True:
        live = [j for j in range(len(members)) if members[j]]
        if len(live) <= 1:
            return
        mean = sum(effort[j] for j in live) / len(live)
        small = min(live, key=lambda j: effort[j])
        if effort[small] >= min_share * mean:
            return
        neighbours = {owner[nb] for lid in members[small] for nb in adj[lid]} - {small}
        if neighbours:
            target = min(neighbours, key=lambda j: effort[j])
        else:
            sx, sy = seeds[small].x, seeds[small].y
            target = min((j for j in live if j != small),
                         key=lambda j: (seeds[j].x - sx) ** 2 + (seeds[j].y - sy) ** 2)
        for lid in members[small]:
            owner[lid] = target
        members[target] |= members[small]
        effort[target] += effort[small]
        members[small], effort[small] = set(), 0.0


def _rebalance(members, effort, owner, adj, by_id, iterations: int = 200) -> None:
    """Move boundary lanes from the heaviest chunk to a lighter neighbouring chunk while that
    narrows the spread. Only moves lanes whose removal keeps the donor chunk connected."""
    for _ in range(iterations):
        heavy = max(range(len(members)), key=lambda j: effort[j])
        best = None
        for lid in members[heavy]:
            for nb in adj[lid]:
                j = owner[nb]
                if j == heavy:
                    continue
                e = by_id[lid].effort
                if effort[j] + e >= effort[heavy]:  # would not reduce the gap
                    continue
                if best is None or effort[j] < effort[best[1]]:
                    best = (lid, j)
        if best is None:
            return
        lid, j = best
        rest = members[heavy] - {lid}
        if rest and not _connected(rest, adj):
            # try once more with a different candidate next time by blocking this lane
            adj = {k: (v - {lid} if k == lid else v) for k, v in adj.items()}
            continue
        members[heavy].discard(lid)
        members[j].add(lid)
        owner[lid] = j
        effort[heavy] -= by_id[lid].effort
        effort[j] += by_id[lid].effort


def _connected(ids: set[str], adj: dict[str, set[str]]) -> bool:
    start = next(iter(ids))
    seen, stack = {start}, [start]
    while stack:
        for nb in adj[stack.pop()]:
            if nb in ids and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(ids)


def balance_ratio(chunks: list[list[str]], lanes: list[Lane]) -> float:
    by_id = {ln.id: ln for ln in lanes}
    efforts = [sum(by_id[i].effort for i in c) for c in chunks if c]
    return max(efforts) / min(efforts) if efforts and min(efforts) > 0 else float("inf")
