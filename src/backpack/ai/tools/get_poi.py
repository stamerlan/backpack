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
        osm_type: "n" (node), "w" (way) or "r" (relation).
        osm_id: numeric OSM id of the element.
        lat, long: coordinates of the point of interest.
        osm_tags: dict of raw OSM tags with the details.

    Args:
        route_id: Id of the route, from get_trip_info.

    Returns None if no route has that id or its POIs are still loading.
    """
    if ctx.deps.doc.route(route_id) is None:
        return None
    poi = ctx.deps.poi.get(route_id)
    if poi is None:
        return None
    return [asdict(p) for p in poi]
