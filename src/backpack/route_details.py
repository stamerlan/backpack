import logging
from collections.abc import Iterable, Iterator
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from typing import Literal

import overpy

from . import model, route
from .overpass import Overpass
from .poi_tiles import PoiTile, tile_bbox, tile_of, tiles_for_track

logger = logging.getLogger(__name__)

POI_SAMPLE_M = 350.0
TILE_BATCH = 12
POI_FILTERS = (
    '[natural~"peak|spring|saddle|cave_entrance|water"]',
    '[tourism~"viewpoint|alpine_hut|wilderness_hut'
    '|attraction|camp_site|picnic_site"]',
    '[amenity~"shelter|drinking_water|toilets|shower"]',
    '[mountain_pass=yes]',
    '[historic]',
)


def _poi_query(tiles: Iterable[PoiTile]) -> str:
    """Build Overpass QL querying POIs in a batch of tile bboxes."""
    lines: list[str] = []
    for tile in tiles:
        s, w, n, e = tile_bbox(tile)
        bbox = f"{s},{w},{n},{e}"
        for f in POI_FILTERS:
            lines.append(f"  nwr{f}({bbox});")
    body = "\n".join(lines)
    return f"[out:json][timeout:180];\n(\n{body}\n);\nout center;\n"


def _raw_pois(
    result: overpy.Result,
) -> Iterator[
    tuple[Literal["n", "w", "r"], int, float, float, dict[str, str]]
]:
    """Yield (osm_type, osm_id, lat, lon, tags) from an overpy result.

    Drops elements that have no tags or no center coordinate.
    """
    for node in result.nodes:
        if node.tags:
            yield (
                "n", node.id,
                float(node.lat), float(node.lon),
                dict(node.tags),
            )
    for way in result.ways:
        if (way.center_lat is not None
                and way.center_lon is not None
                and way.tags):
            yield (
                "w", way.id,
                float(way.center_lat), float(way.center_lon),
                dict(way.tags),
            )
    for rel in result.relations:
        if (rel.center_lat is not None
                and rel.center_lon is not None
                and rel.tags):
            yield (
                "r", rel.id,
                float(rel.center_lat), float(rel.center_lon),
                dict(rel.tags),
            )


def _batch_tiles(
    tiles: frozenset[PoiTile], batch_size: int
) -> list[list[PoiTile]]:
    """Split tiles into batches of at most batch_size."""
    ordered = sorted(tiles, key=lambda t: (t.x, t.y))
    return [
        ordered[i:i + batch_size]
        for i in range(0, len(ordered), batch_size)
    ]


class RouteDetails:
    """Loads route detail data off the mainloop, hiding the Overpass client. """

    def __init__(self) -> None:
        self._overpass = Overpass()
        # Two workers mirror Overpass's own slot budget; more would just block
        # on the server's rate limit anyway.
        self._pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="route-details"
        )

    def load_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> "Future[tuple[model.Poi, ...]]":
        """Start loading POIs near track and return the pending future.

        The future resolves to the POIs found (an empty tuple when none), or
        fails with CancelledError if the service is cancelled while it runs.
        """
        return self._pool.submit(self._fetch_poi, track)

    def cancel(self) -> None:
        """Abort in-flight loads and stop accepting new ones.

        Thread safe, so it may be called from the shutdown handler. Aborting
        Overpass makes each running load raise CancelledError and finish;
        queued loads are dropped.
        """
        self._overpass.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _fetch_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> tuple[model.Poi, ...]:
        """Query Overpass for POIs near the track via tile bboxes.

        Computes tiles covering a corridor of POI_SAMPLE_M around the track,
        batches them into groups of TILE_BATCH, queries Overpass for each batch
        and assigns returned elements to tiles by their center coordinate
        (dropping any whose center falls outside the requested batch). The
        corridor filter is applied locally: only POIs within POI_SAMPLE_M of
        the track are kept.
        """
        sampled_track = route.sample(track, POI_SAMPLE_M)
        if not sampled_track:
            return ()

        tiles = tiles_for_track(sampled_track, POI_SAMPLE_M)
        batches = _batch_tiles(tiles, TILE_BATCH)

        raw: list[tuple[
            Literal["n", "w", "r"], int, float, float,
            dict[str, str]
        ]] = []
        for batch in batches:
            batch_set = frozenset(batch)
            try:
                result = self._overpass.query(_poi_query(batch))
            except Overpass.Aborted:
                raise CancelledError from None
            for osm_type, osm_id, lat, lon, tags in _raw_pois(result):
                if tile_of(lat, lon) not in batch_set:
                    continue
                raw.append((osm_type, osm_id, lat, lon, tags))

        found: list[tuple[float, model.Poi]] = []
        for osm_type, osm_id, lat, lon, tags in raw:
            nearest_pt = route.nearest(lat, lon, track)
            dist_from_track = route.distance_m(
                (lat, lon), nearest_pt
            )
            if dist_from_track > POI_SAMPLE_M:
                continue
            ofs_m = nearest_pt.dist_m
            found.append((
                ofs_m,
                model.Poi(
                    osm_type=osm_type, osm_id=osm_id,
                    lat=lat, long=lon,
                    osm_tags=tags
                )
            ))

        found.sort(key=lambda p: p[0])
        return tuple(p[1] for p in found)
