"""Slippy-map tile arithmetic at a fixed zoom level.

The cache unit is a tile at TILE_Z = 13 (~4.9 km at the equator, ~3.3 km at
alpine latitudes). This module converts between geographic coordinates and tile
indices and computes the set of tiles that cover a buffered corridor along a
track.

A POI belongs to exactly one tile - the one containing its coordinate. Overpass
returns elements intersecting a bbox, so elements whose center falls outside the
tile are dropped on write. That keeps tiles disjoint and writes idempotent.

Known trade-off: a large area feature whose center is far from the route (e.g. a
big lake) lands in a tile that may never be fetched, so it can be missed.
"""
import math
from dataclasses import dataclass
from typing import Iterable

TILE_ZOOM = 13
_N = 1 << TILE_ZOOM

_M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True, slots=True)
class PoiTile:
    """Slippy-map tile index at zoom TILE_Z."""

    x: int
    y: int


def tile_of(lat: float, lon: float) -> PoiTile:
    """Return the tile containing the given coordinate."""
    lat_rad = math.radians(lat)
    x = int((lon + 180.0) / 360.0 * _N)
    y = int(
        (
            1.0
            - math.log(
                math.tan(lat_rad) + 1.0 / math.cos(lat_rad)
            )
            / math.pi
        )
        / 2.0
        * _N
    )
    return PoiTile(
        max(0, min(_N - 1, x)),
        max(0, min(_N - 1, y)),
    )


def tile_bbox(tile: PoiTile) -> tuple[float, float, float, float]:
    """Bounding box of a tile as (south, west, north, east)."""
    west = tile.x / _N * 360.0 - 180.0
    east = (tile.x + 1) / _N * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(
        math.pi * (1.0 - 2.0 * tile.y / _N)
    )))
    south = math.degrees(math.atan(math.sinh(
        math.pi * (1.0 - 2.0 * (tile.y + 1) / _N)
    )))
    return south, west, north, east


def tiles_for_track(
    track: Iterable[tuple[float, float]],
    radius_m: float
) -> frozenset[PoiTile]:
    """Tiles covering a corridor of radius_m around track.

    For each point the tile of the point itself and the tiles of four points
    offset by radius_m (N, S, E, W) are included, so a corridor that only clips
    a tile corner still picks it up.
    """
    tiles = set[PoiTile]()
    for lat, lon in track:
        tiles.add(tile_of(lat, lon))
        dlat = radius_m / _M_PER_DEG_LAT
        dlon = radius_m / (
            _M_PER_DEG_LAT * math.cos(math.radians(lat))
        )
        tiles.add(tile_of(lat + dlat, lon))
        tiles.add(tile_of(lat - dlat, lon))
        tiles.add(tile_of(lat, lon + dlon))
        tiles.add(tile_of(lat, lon - dlon))
    return frozenset(tiles)
