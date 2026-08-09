"""Tests for RouteDetails POI fetching.

_fetch_poi runs against a stubbed Overpass, so no request leaves the machine:
the query string is captured and a canned overpy result is returned. The
transport itself is covered by test_overpass.
"""
import json
from concurrent.futures import CancelledError

import overpy
import pytest

from backpack import model
from backpack.overpass import Overpass
from backpack.poi_tiles import tile_bbox, tile_of, tiles_for_track
from backpack.route_details import (
    POI_FILTERS, POI_SAMPLE_M, TILE_BATCH, RouteDetails,
)


def track_point(lat: float, long: float, dist_m: float) -> model.TrackPoint:
    return model.TrackPoint(
        lat=lat, long=long, elev_m=0.0, slope=0.0, dist_m=dist_m, dur_s=0.0
    )


# A straight west-to-east track; each 0.01 deg of longitude is about 743 m at
# this latitude, so a POI's nearest point tells us where it sorts.
TRACK = (
    track_point(48.0, 24.00, 0.0),
    track_point(48.0, 24.01, 743.0),
    track_point(48.0, 24.02, 1486.0),
)


def node(oid: int, lat: float, lon: float, **tags: str) -> dict[str, object]:
    return {"type": "node", "id": oid, "lat": lat, "lon": lon, "tags": tags}


def way(
    oid: int, lat: float | None, lon: float | None, **tags: str
) -> dict[str, object]:
    el: dict[str, object] = {"type": "way", "id": oid, "tags": tags}
    if lat is not None and lon is not None:
        el["center"] = {"lat": lat, "lon": lon}
    return el


def relation(
    oid: int, lat: float, lon: float, **tags: str
) -> dict[str, object]:
    return {
        "type": "relation", "id": oid,
        "center": {"lat": lat, "lon": lon}, "tags": tags,
    }


def result_from(*elements: dict[str, object]) -> overpy.Result:
    payload = json.dumps({"elements": list(elements)})
    return overpy.Overpass().parse_json(payload)


def make_rd(
    result: overpy.Result | Exception,
) -> tuple[RouteDetails, dict[str, list[str]]]:
    """A RouteDetails whose Overpass.query is stubbed.

    The stub records every QL it receives in the returned dict under "qls",
    and either returns result or raises it when it is an exception.
    """
    rd = RouteDetails()
    captured: dict[str, list[str]] = {"qls": []}

    def fake_query(
        ql: str, timeout_s: float = 90, retries: int = 3
    ) -> overpy.Result:
        captured["qls"].append(ql)
        if isinstance(result, Exception):
            raise result
        return result

    rd._overpass.query = fake_query  # type: ignore[method-assign]
    return rd, captured


def test_fetch_poi_builds_tile_bbox_query() -> None:
    rd, captured = make_rd(result_from())
    rd._fetch_poi(TRACK)

    qls = captured["qls"]
    assert len(qls) >= 1
    ql = qls[0]
    assert "[out:json]" in ql
    assert ql.strip().endswith("out center;")
    for f in POI_FILTERS:
        assert f in ql
    # Must contain bbox coordinates, not around: syntax
    assert "around:" not in ql
    assert "nwr" in ql
    # Verify bbox format (s,w,n,e) appears
    tiles = tiles_for_track(
        ((48.0, 24.0), (48.0, 24.01), (48.0, 24.02)),
        POI_SAMPLE_M,
    )
    for tile in list(tiles)[:1]:
        s, w, n, e = tile_bbox(tile)
        assert f"{s},{w},{n},{e}" in ql


def test_fetch_poi_returns_pois_sorted_from_the_start() -> None:
    rd, _ = make_rd(result_from(
        relation(4, 48.0005, 24.02, amenity="shelter"),
        node(1, 48.0005, 24.00, natural="peak"),
        way(3, 48.0005, 24.01, tourism="alpine_hut"),
    ))
    pois = rd._fetch_poi(TRACK)

    assert [p.osm_tags for p in pois] == [
        {"natural": "peak"},
        {"tourism": "alpine_hut"},
        {"amenity": "shelter"},
    ]
    assert (pois[0].lat, pois[0].long) == (48.0005, 24.00)
    assert [(p.osm_type, p.osm_id) for p in pois] == [
        ("n", 1), ("w", 3), ("r", 4),
    ]


def test_fetch_poi_skips_untagged_and_centerless_elements() -> None:
    rd, _ = make_rd(result_from(
        node(1, 48.0005, 24.00),
        node(2, 48.0005, 24.01, natural="spring"),
        way(3, None, None, tourism="viewpoint"),
    ))
    pois = rd._fetch_poi(TRACK)

    assert [p.osm_tags for p in pois] == [{"natural": "spring"}]
    assert pois[0].osm_type == "n"
    assert pois[0].osm_id == 2


def test_fetch_poi_copies_tags_off_the_overpy_element() -> None:
    result = result_from(node(1, 48.0005, 24.00, natural="peak"))
    result.nodes[0].tags["natural"] = "mutated"
    rd, _ = make_rd(result)

    pois = rd._fetch_poi(TRACK)
    assert pois[0].osm_tags == {"natural": "mutated"}
    pois[0].osm_tags["natural"] = "again"
    assert result.nodes[0].tags["natural"] == "mutated"


def test_fetch_poi_filters_pois_beyond_corridor() -> None:
    """POIs farther than POI_SAMPLE_M from the track are dropped."""
    rd, _ = make_rd(result_from(
        # ~55 m from track - inside corridor
        node(1, 48.0005, 24.00, natural="peak"),
        # ~445 m from track - outside corridor (POI_SAMPLE_M=350)
        node(2, 48.004, 24.01, natural="spring"),
    ))
    pois = rd._fetch_poi(TRACK)

    assert len(pois) == 1
    assert pois[0].osm_id == 1


def test_fetch_poi_empty_track_returns_empty_without_querying() -> None:
    rd, captured = make_rd(result_from())
    assert rd._fetch_poi(()) == ()
    assert captured["qls"] == []


def test_fetch_poi_translates_abort_to_cancelled() -> None:
    rd, _ = make_rd(Overpass.Aborted())
    with pytest.raises(CancelledError):
        rd._fetch_poi(TRACK)


def test_fetch_poi_drops_elements_outside_requested_tiles() -> None:
    """Elements whose center lands in a tile not in the batch are dropped."""
    # This node is far from the track - its tile is not in the set
    # computed by tiles_for_track, so it should be dropped even if
    # Overpass returns it.
    rd, _ = make_rd(result_from(
        node(1, 48.0005, 24.00, natural="peak"),
        node(99, 10.0, 10.0, natural="spring"),
    ))
    pois = rd._fetch_poi(TRACK)

    assert all(p.osm_id != 99 for p in pois)


def test_fetch_poi_batches_tiles() -> None:
    """With more tiles than TILE_BATCH, multiple queries are issued."""
    # Build a long track that spans many tiles
    long_track = tuple(
        track_point(48.0, 24.0 + i * 0.05, i * 3700.0)
        for i in range(20)
    )
    tiles = tiles_for_track(
        tuple((p.lat, p.long) for p in long_track),
        POI_SAMPLE_M,
    )
    expected_batches = (len(tiles) + TILE_BATCH - 1) // TILE_BATCH

    rd, captured = make_rd(result_from())
    rd._fetch_poi(long_track)

    assert len(captured["qls"]) == expected_batches
