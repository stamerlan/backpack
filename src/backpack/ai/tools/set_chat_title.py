from pydantic_ai import RunContext

from ... import model
from ..deps import Deps


def set_chat_title(ctx: RunContext[Deps], title: str) -> str:
    """Set a short title for this chat tab.

    Use a concise label of a few words that captures the topic of the
    conversation, e.g. "Water sources day 2" or "Packing list". Keep title short
    (~30 chars max). Call this once you understand what the chat is about, and
    again if the topic clearly changes.
    """
    with ctx.deps.doc.edit(ctx.deps.agent) as ed:
        ed.apply(model.SetChatTitle(ctx.deps.chat_id, title))
    return "Chat title updated."
