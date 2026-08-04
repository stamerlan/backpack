from pydantic_ai import RunContext

from ... import model
from ..deps import Deps
from .get_trip_info import get_trip_info


def set_route_info(
    ctx: RunContext[Deps],
    route_id: str,
    title: str | None = None,
    notes: str | None = None,
) -> dict[str, object] | None:
    """Update one route's title and/or notes.

    Only provided arguments are changed; omit to keep the current value.
    Call get_trip_info first for a valid route_id.

    Args:
        route_id: from get_trip_info.
        title: new route title (~50 chars max). Omit to keep current.
        notes: new notes (markdown). Omit to keep current.

    Returns None if no route has that id, otherwise the updated trip
    info (same shape as get_trip_info).
    """
    with ctx.deps.doc.edit(ctx.deps.agent) as ed:
        if route_id not in ctx.deps.doc.route_ids():
            return None
        ed.apply(model.SetRouteInfo(route_id, title, notes))
        return get_trip_info(ctx)
