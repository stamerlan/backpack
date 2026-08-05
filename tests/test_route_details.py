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
from backpack.route_details import POI_FILTERS, POI_SAMPLE_M, RouteDetails


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
) -> tuple[RouteDetails, dict[str, str]]:
    """A RouteDetails whose Overpass.query is stubbed.

    The stub records the QL it receives in the returned dict under "ql", and
    either returns result or raises it when it is an exception.
    """
    rd = RouteDetails()
    captured: dict[str, str] = {}

    def fake_query(
        ql: str, timeout_s: float = 90, retries: int = 3
    ) -> overpy.Result:
        captured["ql"] = ql
        if isinstance(result, Exception):
            raise result
        return result

    rd._overpass.query = fake_query  # type: ignore[method-assign]
    return rd, captured


def test_fetch_poi_builds_the_around_query() -> None:
    rd, captured = make_rd(result_from())
    rd._fetch_poi(TRACK)

    ql = captured["ql"]
    assert "[out:json]" in ql
    assert ql.strip().endswith("out center;")
    assert f"nwr(around:{POI_SAMPLE_M * 1.118}," in ql
    assert "48.0,24.0" in ql            # the sampled start coordinate
    for f in POI_FILTERS:
        assert f in ql


def test_fetch_poi_returns_pois_sorted_from_the_start() -> None:
    rd, _ = make_rd(result_from(
        relation(4, 48.0005, 24.02, amenity="shelter"),    # nearest the end
        node(1, 48.0005, 24.00, natural="peak"),           # nearest the start
        way(3, 48.0005, 24.01, tourism="alpine_hut"),      # in the middle
    ))
    pois = rd._fetch_poi(TRACK)

    assert [p.tags for p in pois] == [
        {"natural": "peak"},
        {"tourism": "alpine_hut"},
        {"amenity": "shelter"},
    ]
    assert (pois[0].lat, pois[0].long) == (48.0005, 24.00)
    # 0.0005 deg of latitude off the track is about 55 m
    assert all(40.0 < p.ofs_m < 80.0 for p in pois)


def test_fetch_poi_skips_untagged_and_centerless_elements() -> None:
    rd, _ = make_rd(result_from(
        node(1, 48.0005, 24.00),                    # bare geometry, no tags
        node(2, 48.0005, 24.01, natural="spring"),
        way(3, None, None, tourism="viewpoint"),    # no center from out center
    ))
    pois = rd._fetch_poi(TRACK)

    assert [p.tags for p in pois] == [{"natural": "spring"}]


def test_fetch_poi_copies_tags_off_the_overpy_element() -> None:
    result = result_from(node(1, 48.0005, 24.00, natural="peak"))
    result.nodes[0].tags["natural"] = "mutated"
    rd, _ = make_rd(result)

    pois = rd._fetch_poi(TRACK)
    assert pois[0].tags == {"natural": "mutated"}
    pois[0].tags["natural"] = "again"
    assert result.nodes[0].tags["natural"] == "mutated"


def test_fetch_poi_empty_track_returns_empty_without_querying() -> None:
    rd, captured = make_rd(result_from())
    assert rd._fetch_poi(()) == ()
    assert "ql" not in captured


def test_fetch_poi_translates_abort_to_cancelled() -> None:
    rd, _ = make_rd(Overpass.Aborted())
    with pytest.raises(CancelledError):
        rd._fetch_poi(TRACK)
