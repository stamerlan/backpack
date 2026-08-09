from dataclasses import asdict

from pydantic_ai import RunContext

from ... import route
from ..deps import Deps


def get_trip_info(
    ctx: RunContext[Deps], poi: bool = False
) -> dict[str, object]:
    """Return the whole trip: title, notes and every route.

    Call this first to learn what the trip contains and which routes exist.
    Never invent route ids - take them from each route's "id".

    Set poi=True to include each route's points of interest in one call (water,
    shelters, peaks, huts, viewpoints...). A route's "poi" is None while it is
    still loading asynchronously; tell the user they are loading rather than
    guessing. With poi=False (default) the "poi" key is omitted; use get_poi
    later to fetch it for a single route.

    Args:
        poi: Set True to include points of interest for every route.

    Returns a dict with keys:
        title: trip title (may be empty).
        notes: trip markdown notes (may be empty).
        routes: list of route dicts in trip order, each with:
            id: route id string for set_route_info and get_poi.
            title: route title.
            notes: route notes markdown.
            start, end: first/last TrackPoint dict (lat, long, elev_m, slope,
                dist_m, dur_s).
            stats: route totals:
                dist_m: length in metres, elevation included.
                dur_s: estimated hiking time in seconds.
                ascent_m, descent_m: cumulative climb and drop in metres.
                vertical_m: ascent_m + descent_m, an effort proxy.
                elev_min_m, elev_max_m: lowest and highest point.
                elev_net_m: end minus start elevation, signed.
                elev_mean_m: elevation averaged over distance.
            poi: list of POI dicts (osm_type, osm_id, lat,
                long, osm_tags), or None while still loading.
                Present only when poi=True was requested.
    """
    with ctx.deps.doc.lock():
        return {
            "title": ctx.deps.doc.title,
            "notes": ctx.deps.doc.notes,
            "routes": [
                {
                    "id": r.id,
                    "title": r.title,
                    "notes": r.notes,
                    "start": (r.track[0] if r.track else None),
                    "end": (r.track[-1] if r.track else None),
                    "stats": (
                        route.RouteStats.from_track(r.track)
                        if r.track else None
                    ),
                } | (
                    {"poi": (
                        [asdict(p) for p in r.poi]
                        if r.poi is not None else None
                    )} if poi else {}
                )
                for r in ctx.deps.doc.routes()
            ],
        }
