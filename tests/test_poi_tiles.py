"""Tests for backpack.poi_tiles - slippy-map tile arithmetic."""
from backpack.poi_tiles import (
    TILE_ZOOM,
    PoiTile,
    tile_bbox,
    tile_of,
    tiles_for_track,
)

_N = 1 << TILE_ZOOM


class TestTileOf:
    def test_equator_prime_meridian(self) -> None:
        t = tile_of(0.0, 0.0)
        assert t == PoiTile(_N // 2, _N // 2)

    def test_result_in_valid_range(self) -> None:
        for lat, lon in [
            (47.26, 11.39), (-33.86, 151.21),
            (60.17, 24.94), (0.0, -179.9),
        ]:
            t = tile_of(lat, lon)
            assert 0 <= t.x < _N
            assert 0 <= t.y < _N

    def test_northern_hemisphere_y_below_midpoint(self) -> None:
        t = tile_of(48.0, 12.0)
        assert t.y < _N // 2

    def test_southern_hemisphere_y_above_midpoint(self) -> None:
        t = tile_of(-33.86, 151.21)
        assert t.y > _N // 2

    def test_western_hemisphere_x_below_midpoint(self) -> None:
        t = tile_of(40.7, -74.0)
        assert t.x < _N // 2

    def test_clamps_at_antimeridian(self) -> None:
        t = tile_of(0.0, -180.0)
        assert t.x == 0
        t = tile_of(0.0, 179.99)
        assert t.x == _N - 1


class TestTileBbox:
    def test_round_trip_containment(self) -> None:
        """A point must lie inside its own tile's bbox."""
        coords = [
            (48.0, 24.0), (0.0, 0.0), (47.26, 11.39),
            (-33.86, 151.21), (60.17, 24.94),
        ]
        for lat, lon in coords:
            t = tile_of(lat, lon)
            s, w, n, e = tile_bbox(t)
            assert s <= lat <= n, (
                f"lat {lat} not in [{s}, {n}]"
            )
            assert w <= lon <= e, (
                f"lon {lon} not in [{w}, {e}]"
            )

    def test_south_less_than_north(self) -> None:
        s, w, n, e = tile_bbox(PoiTile(4096, 4096))
        assert s < n
        assert w < e

    def test_tile_width_at_equator(self) -> None:
        """At z=13 a tile spans exactly 360/8192 degrees."""
        s, w, n, e = tile_bbox(PoiTile(4096, _N // 2))
        expected = 360.0 / _N
        assert abs((e - w) - expected) < 1e-9

    def test_adjacent_tiles_share_edge(self) -> None:
        _, _, _, east_a = tile_bbox(PoiTile(100, 100))
        _, west_b, _, _ = tile_bbox(PoiTile(101, 100))
        assert abs(east_a - west_b) < 1e-12


class TestTilesForTrack:
    def test_empty_track(self) -> None:
        assert tiles_for_track([], 500.0) == frozenset()

    def test_single_point_zero_radius(self) -> None:
        tiles = tiles_for_track([(48.0, 24.0)], 0.0)
        assert len(tiles) == 1
        assert tile_of(48.0, 24.0) in tiles

    def test_center_tile_always_present(self) -> None:
        tiles = tiles_for_track([(48.0, 24.0)], 500.0)
        assert tile_of(48.0, 24.0) in tiles

    def test_radius_picks_up_neighbor(self) -> None:
        """A point near a tile edge with enough radius must
        include the neighboring tile."""
        t = tile_of(48.0, 24.0)
        s, w, n, e = tile_bbox(t)
        dlat = 10.0 / 111_320.0
        near_south_edge = (s + dlat, (w + e) / 2)
        narrow = tiles_for_track([near_south_edge], 5.0)
        wide = tiles_for_track([near_south_edge], 500.0)
        assert len(wide) > len(narrow)

    def test_returns_frozenset(self) -> None:
        result = tiles_for_track([(48.0, 24.0)], 350.0)
        assert isinstance(result, frozenset)

    def test_long_track_spans_multiple_x_tiles(self) -> None:
        """A 2-degree east-west track at z=13 must span
        multiple x-tile columns."""
        pts = [
            (48.0, 11.0 + i * 0.1) for i in range(20)
        ]
        tiles = tiles_for_track(pts, 350.0)
        xs = {t.x for t in tiles}
        assert len(xs) > 1

    def test_multiple_points_union(self) -> None:
        """Result is the union of tiles for each point."""
        a = tiles_for_track([(48.0, 11.0)], 0.0)
        b = tiles_for_track([(48.0, 13.0)], 0.0)
        both = tiles_for_track(
            [(48.0, 11.0), (48.0, 13.0)], 0.0
        )
        assert a | b == both
