from dataclasses import asdict

from pydantic_ai import RunContext

from ..deps import Deps


def get_poi(
    ctx: RunContext[Deps], route_id: str
) -> list[dict[str, object]] | None:
    """Return the points of interest near one route.

    POIs (water, shelters, peaks, huts, viewpoints...) load asynchronously after
    the track, so this may be None while still loading; tell the user they are
    loading rather than guessing.

    Each POI dict contains:
        lat, long: coordinates of the point of interest.
        ofs_m: distance in meters from the route track to the POI.
        tags: dict of raw OSM tags with the details.

    Args:
        route_id: Id of the route, from get_trip_info.

    Returns None if no route has that id or its POIs are still loading.
    """
    route = ctx.deps.doc.route(route_id)
    if route is None or route.poi is None:
        return None
    return [asdict(p) for p in route.poi]
