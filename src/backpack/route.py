import math
from dataclasses import dataclass
from typing import Iterable

import gpxpy
import gpxpy.geo
from geopy.distance import geodesic

from . import model


@dataclass(frozen=True, slots=True)
class RouteStats:
    dist_m: float       # route length including elevation, meters
    dur_s: float        # estimated hiking time, seconds
    ascent_m: float     # cumulative climb, noise filtered, positive
    descent_m: float    # cumulative drop, noise filtered, positive
    vertical_m: float   # ascent + descent, single effort proxy
    elev_min_m: float
    elev_max_m: float
    elev_net_m: float   # end minus start, signed
    elev_mean_m: float  # averaged over distance, not over points

    @classmethod
    def from_track(
        cls, track: Iterable[model.TrackPoint], gain_threshold_m: float = 3.0
    ) -> "RouteStats":
        """Aggregate elevation and effort numbers for one track.

        :param track: Track points, as produced by parse_gpx().
        :param float gain_threshold_m: Reversal in metres a run of the profile
            must show before it counts as a real climb or drop. Raise it for
            noisy barometric tracks, lower it for smooth DEM sampled ones.
            See _gain_loss() for why this exists.
        :returns: Totals for the whole track.
        :rtype: RouteStats
        :raises ValueError: If the track has no points.
        """
        track = list(track)
        if not track:
            raise ValueError("track is empty")

        elev = [p.elev_m for p in track]
        ascent_m, descent_m = _gain_loss(elev, gain_threshold_m)
        return cls(
            dist_m=track[-1].dist_m,
            dur_s=track[-1].dur_s,
            ascent_m=ascent_m,
            descent_m=descent_m,
            vertical_m=ascent_m + descent_m,
            elev_min_m=min(elev),
            elev_max_m=max(elev),
            elev_net_m=elev[-1] - elev[0],
            elev_mean_m=_mean_elev(track),
        )


@dataclass(frozen=True, slots=True)
class GpxRoute:
    name: str
    description: str
    track: tuple[model.TrackPoint, ...]


def parse_gpx(text: str) -> GpxRoute:
    """Parse a GPX file into a GpxRoute.

    Reads the file's name and description and converts every track point into
    a model TrackPoint, computing cumulative distance, estimated arrival time
    and per segment slope along the way. The name and description fall back to
    the first track's when the file carries no metadata level ones.

    :raises ValueError: If the file holds no track points.
    """
    gpx = gpxpy.parse(text)
    gpx_points = [
        p for trk in gpx.tracks
          for seg in trk.segments
          for p in seg.points
    ]
    if not gpx_points:
        raise ValueError("No track points")

    name = gpx.name or gpx.tracks[0].name or ""
    description = gpx.description or gpx.tracks[0].description or ""

    track = list[model.TrackPoint]()
    track.append(model.TrackPoint(
        lat=gpx_points[0].latitude,
        long=gpx_points[0].longitude,
        slope=0.0,
        elev_m=gpx_points[0].elevation or 0.0,
        dist_m=0.0,
        dur_s=0.0
    ))

    total_dist_m, total_dur_s = 0.0, 0.0
    for a, b in zip(gpx_points, gpx_points[1:]):
        d_m = distance_m(a, b)
        dh_m = (b.elevation or 0) - (a.elevation or 0)

        total_dist_m += math.sqrt(d_m * d_m + dh_m * dh_m)
        total_dur_s  += hike_time(d_m, dh_m)

        track.append(model.TrackPoint(
            lat=b.latitude,
            long=b.longitude,
            elev_m=b.elevation or 0.0,
            slope=(dh_m / d_m * 100) if d_m else 0.0,
            dist_m=total_dist_m,
            dur_s=total_dur_s
        ))
    return GpxRoute(
        name=name.strip(), description=description.strip(), track=tuple(track)
    )


def distance_m(
    a: tuple[float, float] | model.TrackPoint | gpxpy.geo.Location,
    b: tuple[float, float] | model.TrackPoint | gpxpy.geo.Location,
) -> float:
    """Calculate distance between two points"""
    if isinstance(a, model.TrackPoint):
        a = (a.lat, a.long)
    elif isinstance(a, gpxpy.geo.Location):
        a = (a.latitude, a.longitude)

    if isinstance(b, model.TrackPoint):
        b = (b.lat, b.long)
    elif isinstance(b, gpxpy.geo.Location):
        b = (b.latitude, b.longitude)

    return float(geodesic(a, b).meters)


def hike_time(d_m: float, dh_m: float, slowdown_factor: float = 1.33) -> float:
    """Tobler's Hiking Function.

    Developed by geographer Waldo Tobler in 1993, this formula takes a
    mathematical approach based on the physics of walking. Unlike Book Time and
    Naismith (which are empirical observations), Tobler's function models how
    slope angle affects walking speed.

    Tobler's function recognizes that:
      - Flat ground: You walk at a moderate pace (~5-6 km/h)
      - Gentle downhill (-5% grade): You walk fastest (~6 km/h)
      - Steep uphill: You slow down exponentially
      - Steep downhill: You also slow down (watching your footing)

    :param float d_m: Horizontal segment length in metres.
    :param float dh_m: Elevation delta over the segment in metres.
        Positive values mean ascent, negative values descent.
    :param float slowdown_factor: Multiplier applied to the computed time.
        Tobler's function models the maximum pace of a fit, unladen walker on
        open terrain, so it runs optimistic for real hiking. Use 1.0 for raw
        Tobler; values above 1.0 add time for pack weight, rests, trail surface
        and fatigue. The default is 1.33.
    :returns: Walking time across the segment in seconds.
    :rtype: float
    """
    if d_m == 0:
        return 0.0
    slope = dh_m / d_m
    speed_kmh = 6.0 * math.exp(-3.5 * abs(slope + 0.05))
    return d_m / (speed_kmh * 1000 / 3600) * slowdown_factor


def _gain_loss(elev: list[float], threshold_m: float) -> tuple[float, float]:
    """Cumulative climb and drop with sub-threshold wiggle removed.

    Tracks the extreme reached since the last confirmed reversal and banks it
    only when the profile turns back by threshold_m, so a reversal has to be
    real to register. Banked runs chain end to end, which makes ascent minus
    descent equal the net elevation change exactly - a cheap invariant worth
    asserting in a test.

    :param list[float] elev: Elevation per track point in metres.
    :param float threshold_m: Reversal needed to bank a run.
    :returns: Ascent and descent totals in metres, both positive.
    :rtype: tuple[float, float]
    """
    ascent_m = descent_m = 0.0
    anchor = extreme = elev[0]
    up = True   # a wrong guess banks a zero run and self corrects
    for e in elev[1:]:
        if up:
            if e > extreme:
                extreme = e
            elif extreme - e >= threshold_m:
                ascent_m += extreme - anchor
                anchor, extreme, up = extreme, e, False
        else:
            if e < extreme:
                extreme = e
            elif e - extreme >= threshold_m:
                descent_m += anchor - extreme
                anchor, extreme, up = extreme, e, True

    leg = elev[-1] - anchor
    if leg > 0:
        ascent_m += leg
    else:
        descent_m -= leg
    return ascent_m, descent_m


def bbox(
    points: Iterable[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Bounding box of (lat, long) pairs.

    Returns (south, west, north, east).
    Raises ValueError if the iterable is empty.
    """
    it = iter(points)
    try:
        lat, lng = next(it)
    except StopIteration:
        raise ValueError("no points")
    south = north = lat
    west = east = lng
    for lat, lng in it:
        if lat < south:
            south = lat
        elif lat > north:
            north = lat
        if lng < west:
            west = lng
        elif lng > east:
            east = lng
    return south, west, north, east


def _mean_elev(track: list[model.TrackPoint]) -> float:
    """Elevation averaged over distance rather than over points.

    Point spacing varies by more than an order of magnitude, and the dense
    stretches are the steep ones, so a plain average over elev_m is biased.
    Integrating trapezoidally over the cumulative dist_m already on each point
    costs one pass and removes the bias.
    """
    total_m = track[-1].dist_m
    if total_m <= 0:
        return track[0].elev_m
    area = sum(
        (a.elev_m + b.elev_m) / 2 * (b.dist_m - a.dist_m)
        for a, b in zip(track, track[1:])
    )
    return area / total_m
