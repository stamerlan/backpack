from pydantic_ai import RunContext

from ... import model
from ..assist_run import AssistRun


def set_chat_title(ctx: RunContext[AssistRun], title: str) -> str:
    """Set a title for this chat.

    Use a clear label that captures the topic of the conversation, e.g.
    "Water sources on day 2" or "Packing list for the ridge traverse". Keep it
    to a single line (up to ~60 chars). Call this once you understand what the
    chat is about, and again if the topic clearly changes.
    """
    with ctx.deps.doc.edit(ctx.deps.agent) as ed:
        ed.apply(model.SetChatTitle(ctx.deps.chat_id, title))
    return "Chat title updated."
