from pydantic_ai import RunContext

from ... import model
from ..assist_run import AssistRun
from .get_trip_info import get_trip_info


def set_trip_info(
    ctx: RunContext[AssistRun],
    title: str | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    """Update the trip's title and/or notes.

    Only provided arguments are changed; omit to keep the current value.

    Args:
        title: new trip title (~50 chars max). Omit to keep current.
        notes: new trip notes (markdown). Omit to keep current.

    Returns the updated trip info (same shape as get_trip_info).
    """
    with ctx.deps.doc.edit(ctx.deps.agent) as ed:
        ed.apply(model.SetDocInfo(title, notes))
        return get_trip_info(ctx)
