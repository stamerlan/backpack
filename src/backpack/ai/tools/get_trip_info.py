from pydantic_ai import RunContext

from ... import route
from ..deps import Deps


def get_trip_info(ctx: RunContext[Deps]) -> dict[str, object]:
    """Return the whole trip: title, notes and every route.

    Call this first to learn what the trip contains and which routes exist.
    Never invent route ids - take them from each route's "id".

    Returns a dict with keys:
        title: trip title (may be empty).
        notes: trip markdown notes (may be empty).
        routes: list of route dicts in trip order, each with:
            id: route id string for set_route_info.
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
                }
                for r in ctx.deps.doc.routes()
            ],
        }
