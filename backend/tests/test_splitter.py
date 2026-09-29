"""Splitter on a synthetic street grid: partition, contiguity, balance."""

from app.services.splitter import Lane, _connected, adjacency, balance_ratio, split


def grid(n: int = 12, block_m: float = 100.0) -> list[Lane]:
    """n x n street grid; nodes are intersections, lanes are block edges."""
    node = lambda i, j: i * 1000 + j  # noqa: E731
    lanes = []
    for i in range(n):
        for j in range(n):
            if j + 1 < n:
                lanes.append(Lane(f"h{i}_{j}", block_m, "residential", node(i, j), node(i, j + 1),
                                  (j + 0.5) * block_m, i * block_m))
            if i + 1 < n:
                lanes.append(Lane(f"v{i}_{j}", block_m, "residential", node(i, j), node(i + 1, j),
                                  j * block_m, (i + 0.5) * block_m))
    return lanes


def test_partition_covers_every_lane_exactly_once():
    lanes = grid()
    chunks = split(lanes, target_effort_m=3000)
    flat = [lid for c in chunks for lid in c]
    assert sorted(flat) == sorted(ln.id for ln in lanes)
    assert len(flat) == len(set(flat))


def test_chunk_count_follows_effort():
    lanes = grid()  # 264 lanes x 100 m = 26.4 km
    assert len(split(lanes, target_effort_m=3000)) == 9
    assert len(split(lanes, target_effort_m=100_000)) == 1


def test_chunks_are_contiguous_and_balanced():
    lanes = grid()
    adj = adjacency(lanes)
    chunks = split(lanes, target_effort_m=3000)
    assert all(_connected(set(c), adj) for c in chunks)
    assert balance_ratio(chunks, lanes) <= 1.6


def test_disconnected_islands_still_assigned():
    lanes = grid(4) + [Lane("island", 80, "residential", 999_001, 999_002, 5000, 5000)]
    chunks = split(lanes, target_effort_m=600)
    assert any("island" in c for c in chunks)
