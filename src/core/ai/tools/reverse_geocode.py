import logging

from geopy.exc import GeopyError
from pydantic_ai import RunContext

from ...nominatim import Nominatim
from ..assist_run import AssistRun

logger = logging.getLogger(__name__)


def reverse_geocode(
    ctx: RunContext[AssistRun], lat: float, long: float
) -> dict[str, object] | str:
    """Resolve coordinates to a place name and address via OpenStreetMap.

    Use to label a track point, POI or camp with its nearest settlement, valley,
    region and country. This does NOT give opening hours, services or whether a
    place still operates - use google_maps for those.

    Returns a dict with keys name, display_name and address (a dict of OSM
    address parts like village, county, state, country), or a message when the
    point cannot be resolved.

    Args:
        lat: latitude in decimal degrees.
        long: longitude in decimal degrees.
    """
    try:
        place = ctx.deps.agent.nominatim.reverse(lat, long)
    except Nominatim.Aborted:
        return "Place lookup was canceled."
    except GeopyError as e:
        logger.error(e)
        return "Place lookup failed, tell the user to try again."
    if place is None:
        return f"No place found at {lat},{long}."
    return {
        "name": place.get("name", ""),
        "display_name": place.get("display_name", ""),
        "address": place.get("address", {}),
    }
