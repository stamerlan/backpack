from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Iterator
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Literal

import overpy

from . import model, route
from .overpass import Overpass
from .poi_tiles import PoiTile, tile_bbox, tile_of, tiles_for_track
from .storage.poi_cache import CachedPoi, filters_hash

if TYPE_CHECKING:
    from .storage.poi_cache import PoiCache

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
    """Loads route detail data off the mainloop, hiding the Overpass client and
    tile cache.
    """

    def __init__(self, cache: PoiCache | None = None) -> None:
        self._overpass = Overpass()
        self._cache = cache
        # Two workers mirror Overpass's own slot budget; more would
        # just block on the server's rate limit anyway.
        self._pool = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="route-details"
        )
        # Per-tile in-flight dedup: when one worker is already
        # fetching a tile, the other waits on the same future
        # instead of issuing a duplicate request.
        self._inflight: dict[PoiTile, Future[list[CachedPoi]]] = {}
        self._inflight_lock = threading.Lock()
        # Background refresher for stale tiles. Single thread so it never
        # competes with the foreground pool for Overpass slots.
        self._refresher = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="poi-refresh"
        )

    def load_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> Future[tuple[model.Poi, ...]]:
        """Start loading POIs near track and return the pending future.

        The future resolves to the POIs found (an empty tuple when
        none), or fails with CancelledError if the service is
        cancelled while it runs.
        """
        return self._pool.submit(self._fetch_poi, track)

    def cancel(self) -> None:
        """Abort in-flight loads and stop accepting new ones.

        Thread safe, so it may be called from the shutdown handler.
        Aborting Overpass makes each running load raise
        CancelledError and finish; queued loads are dropped.
        The background refresher is shut down too.
        """
        self._overpass.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._refresher.shutdown(wait=False, cancel_futures=True)

    def _fetch_tiles(
        self, tiles_to_fetch: frozenset[PoiTile]
    ) -> dict[PoiTile, list[CachedPoi]]:
        """Fetch POIs for *tiles_to_fetch* from Overpass, deduping against other
        in-flight fetches in this process.

        Returns a dict mapping each tile to its POIs.
        """
        # Partition tiles into ones already in-flight and ones we
        # need to fetch ourselves.
        owned: list[PoiTile] = []
        waited: dict[PoiTile, Future[list[CachedPoi]]] = {}

        with self._inflight_lock:
            for tile in tiles_to_fetch:
                existing = self._inflight.get(tile)
                if existing is not None:
                    waited[tile] = existing
                else:
                    fut: Future[list[CachedPoi]] = Future()
                    self._inflight[tile] = fut
                    owned.append(tile)

        result: dict[PoiTile, list[CachedPoi]] = {}

        # Fetch our owned tiles from Overpass in batches.
        try:
            fetched = self._fetch_tiles_from_overpass(owned)
            for tile in owned:
                pois = fetched.get(tile, [])
                result[tile] = pois
                with self._inflight_lock:
                    self._inflight[tile].set_result(pois)
                    del self._inflight[tile]
        except BaseException as exc:
            # Signal waiters so they don't hang.
            with self._inflight_lock:
                for tile in owned:
                    fut_owned = self._inflight.pop(tile, None)
                    if fut_owned is not None and not fut_owned.done():
                        fut_owned.set_exception(exc)
            raise

        # Collect results from tiles another worker was fetching.
        for tile, fut_ext in waited.items():
            try:
                result[tile] = fut_ext.result()
            except CancelledError:
                raise
            except Exception:
                # Treat a peer failure as a miss - the tile simply
                # won't contribute POIs this time.
                result[tile] = []

        return result

    def _fetch_tiles_from_overpass(
        self, tiles: list[PoiTile]
    ) -> dict[PoiTile, list[CachedPoi]]:
        """Query Overpass for POIs in the given tiles.

        Tiles are split into batches of TILE_BATCH. Each returned element is
        assigned to a tile by its center coordinate; elements outside the batch
        are dropped.
        """
        if not tiles:
            return {}
        batches = _batch_tiles(frozenset(tiles), TILE_BATCH)
        per_tile: dict[PoiTile, list[CachedPoi]] = {
            t: [] for t in tiles
        }
        for batch in batches:
            batch_set = frozenset(batch)
            try:
                result = self._overpass.query(_poi_query(batch))
            except Overpass.Aborted:
                raise CancelledError from None
            for osm_type, osm_id, lat, lon, tags in (
                _raw_pois(result)
            ):
                tile = tile_of(lat, lon)
                if tile not in batch_set:
                    continue
                per_tile.setdefault(tile, []).append(CachedPoi(
                    osm_type=osm_type,
                    osm_id=osm_id,
                    lat=lat,
                    long=lon,
                    tags=tags,
                ))
        return per_tile

    def _schedule_refresh(
        self, stale: frozenset[PoiTile], cur_filters: int
    ) -> None:
        """Submit stale tiles for background refresh."""
        to_refresh = sorted(stale, key=lambda t: (t.x, t.y))
        logger.debug(f"scheduling refresh for {len(to_refresh)} stale tiles")
        self._refresher.submit(self._refresh_tiles, to_refresh, cur_filters)

    def _refresh_tiles(self, tiles: list[PoiTile], cur_filters: int) -> None:
        """Fetch tiles from Overpass and write to cache.

        Runs on the refresher thread. All errors are swallowed so a failing
        refresh never disrupts foreground work.
        """
        try:
            fetched = self._fetch_tiles_from_overpass(tiles)
            assert self._cache is not None
            for tile, pois in fetched.items():
                try:
                    self._cache.put(tile, pois, cur_filters)
                except Exception:
                    logger.debug(
                        f"refresh write failed for tile {tile}",
                        exc_info=True
                    )
            logger.debug(f"refreshed {len(fetched)} stale tiles")
        except CancelledError:
            pass
        except Exception:
            logger.debug("background refresh failed", exc_info=True)

    def _fetch_poi(
        self, track: tuple[model.TrackPoint, ...]
    ) -> tuple[model.Poi, ...]:
        """Query for POIs near the track, using the tile cache when
        available.

        Computes tiles covering a corridor of POI_SAMPLE_M around the track.
        When a cache is present, serves hits directly and only fetches misses
        from Overpass. Freshly fetched tiles are written back to the cache, and
        all used tiles get a touch.
        """
        sampled_track = route.sample(track, POI_SAMPLE_M)
        if not sampled_track:
            return ()

        tiles = tiles_for_track(sampled_track, POI_SAMPLE_M)
        cur_filters = filters_hash(POI_FILTERS)

        # Read through cache
        cached_pois: dict[PoiTile, list[CachedPoi]] = {}
        missing: frozenset[PoiTile] = tiles
        stale: frozenset[PoiTile] = frozenset()

        if self._cache is not None:
            try:
                cached_pois, missing, stale = self._cache.get(
                    tiles, cur_filters
                )
            except Exception:
                logger.debug(
                    "poi cache read failed, treating all as miss",
                    exc_info=True
                )
                missing = tiles

        logger.debug(
            f"poi tiles:{len(tiles)}, {len(cached_pois)} cached, "
            f"{len(missing)} missing"
        )

        # Fetch misses from Overpass (with in-flight dedup)
        fetched: dict[PoiTile, list[CachedPoi]] = {}
        if missing:
            fetched = self._fetch_tiles(missing)

        # Write fetched tiles back to cache
        if self._cache is not None and fetched:
            for tile, pois in fetched.items():
                try:
                    self._cache.put(tile, pois, cur_filters)
                except Exception:
                    logger.debug(
                        "poi cache write failed for tile %s",
                        tile, exc_info=True,
                    )

        # Touch all tiles we used (hits + fetched)
        if self._cache is not None:
            touched = frozenset(cached_pois.keys()) | frozenset(fetched)
            try:
                self._cache.touch(touched)
            except Exception:
                logger.debug("poi cache touch failed", exc_info=True)

        # Background-refresh stale tiles
        if self._cache is not None and stale:
            self._schedule_refresh(stale, cur_filters)

        # Merge cached and fetched POIs
        all_pois: dict[PoiTile, list[CachedPoi]] = {}
        all_pois.update(cached_pois)
        all_pois.update(fetched)

        # Corridor filter + offset computation
        found: list[tuple[float, model.Poi]] = []
        for tile_pois in all_pois.values():
            for cp in tile_pois:
                nearest_pt = route.nearest(cp.lat, cp.long, track)
                dist_from_track = route.distance_m(
                    (cp.lat, cp.long), nearest_pt
                )
                if dist_from_track > POI_SAMPLE_M:
                    continue
                ofs_m = nearest_pt.dist_m
                found.append((
                    ofs_m,
                    model.Poi(
                        osm_type=cp.osm_type,
                        osm_id=cp.osm_id,
                        lat=cp.lat,
                        long=cp.long,
                        osm_tags=cp.tags,
                    )
                ))

        found.sort(key=lambda p: p[0])
        return tuple(p[1] for p in found)
