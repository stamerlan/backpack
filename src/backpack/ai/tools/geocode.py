import logging

from geopy.exc import GeopyError
from pydantic_ai import RunContext

from ...nominatim import Nominatim
from ..deps import Deps

logger = logging.getLogger(__name__)


def geocode(ctx: RunContext[Deps], query: str) -> dict[str, object] | str:
    """Resolve a place name to coordinates via OpenStreetMap.

    Use to put a named place on the map: a village, pass, lake, hut or trail
    head. Name the region and the country in the query to avoid ambiguity, e.g.
    "Zakopane, Poland". This does NOT give opening hours, services or whether a
    place still operates - use google_maps for those.

    Returns a dict with keys lat, long, name, display_name and address (a dict
    of OSM address parts like village, county, state, country), or a message
    when the place cannot be resolved.

    Args:
        query: free-form place name.
    """
    try:
        place = ctx.deps.agent.nominatim.search(query)
    except Nominatim.Aborted:
        return "Place lookup was canceled."
    except GeopyError as e:
        logger.error(e)
        return "Place lookup failed, tell the user to try again."
    if place is None:
        return f"No place found for {query!r}."
    try:
        lat, long = float(place["lat"]), float(place["lon"])
    except (KeyError, TypeError, ValueError):
        return f"No coordinates for {query!r}."
    return {
        "lat": lat,
        "long": long,
        "name": place.get("name", ""),
        "display_name": place.get("display_name", ""),
        "address": place.get("address", {}),
    }
