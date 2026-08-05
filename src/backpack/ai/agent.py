from typing import Callable, TYPE_CHECKING

import pydantic_ai
import pydantic_ai.capabilities

from . import prompts, provider, tools
from .deps import Deps
from .errors import AiError

if TYPE_CHECKING:
    from .. import model
    from ..nominatim import Nominatim
    from ..storage import Storage


def _build_history(
    chat: "model.ChatData",
) -> list[pydantic_ai.ModelMessage]:
    """Map persisted chat turns to pydantic-ai message history.

    Each turn contributes the user prompt and a single assistant message with
    its reply blocks joined. A turn that produced no reply (e.g. a failed run)
    is skipped so the history never carries a dangling user message. Thinking
    and card items never enter the LLM context.
    """
    from ..model.data import ChatReply

    messages = list[pydantic_ai.ModelMessage]()
    for turn in chat.turns:
        reply = "".join(
            it.text for it in turn.items if isinstance(it, ChatReply)
        )
        if not reply:
            continue
        messages.append(pydantic_ai.ModelRequest(
            parts=[pydantic_ai.UserPromptPart(content=turn.prompt)]
        ))
        messages.append(pydantic_ai.ModelResponse(
            parts=[pydantic_ai.TextPart(content=reply)]
        ))
    return messages


class Agent:
    def __init__(self, storage: "Storage", nominatim: "Nominatim") -> None:
        self.storage = storage
        self.nominatim = nominatim
        self.agent = pydantic_ai.Agent[Deps, str](
            deps_type=Deps,
            instructions=prompts.SYSTEM,
            capabilities=[
                pydantic_ai.capabilities.Thinking(effort="medium"),
                pydantic_ai.capabilities.WebSearch(),
            ],
        )

        self.agent.instructions(self._get_chat_title)
        self.agent.tool(tools.geocode)
        self.agent.tool(tools.get_trip_info)
        self.agent.tool(tools.google_maps)
        self.agent.tool(tools.reverse_geocode)
        self.agent.tool(tools.set_chat_title)
        self.agent.tool(tools.set_route_info)
        self.agent.tool(tools.set_trip_info)

    async def ask(
        self,
        doc: "model.Document",
        chat_id: str,
        model_id: str,
        prompt: str,
        on_text: Callable[[str], None] = lambda _: None,
        on_think: Callable[[str], None] = lambda _: None,
        on_tool: Callable[[str], None] = lambda _: None,
    ) -> str:
        """Run the agent and stream tokens back via callbacks.

        on_tool is called with the tool function name each time the
        model invokes a tool, so the caller can emit a status card.
        """
        llm = await provider.build_model(model_id, self.storage)
        if (chat := doc.chat(chat_id)) is None:
            raise AiError(f"No chat id:{chat_id}")

        deps = Deps(self, doc, chat_id, model_id)
        reply = list[str]()
        try:
            async with llm:
                async with self.agent.run_stream_events(
                    prompt,
                    deps=deps,
                    model=llm,
                    message_history=_build_history(chat),
                ) as events:
                    async for ev in events:
                        self._dispatch_event(
                            ev, reply, on_text, on_think, on_tool
                        )
        except AiError:
            raise
        except Exception as e:
            raise AiError.convert(e) from e

        if not reply:
            raise AiError("The model returned an empty reply.", True)
        return "".join(reply)

    def _dispatch_event(
        self,
        ev: object,
        reply: list[str],
        on_text: Callable[[str], None],
        on_think: Callable[[str], None],
        on_tool: Callable[[str], None],
    ) -> None:
        match ev:
            case pydantic_ai.PartStartEvent(
                part=pydantic_ai.TextPart(content=text)
            ) if text:
                reply.append(text)
                on_text(text)
            case pydantic_ai.PartDeltaEvent(
                delta=pydantic_ai.TextPartDelta(content_delta=text)
            ) if text:
                reply.append(text)
                on_text(text)
            case pydantic_ai.PartStartEvent(
                part=pydantic_ai.ThinkingPart(content=text)
            ) if text:
                on_think(text)
            case pydantic_ai.PartDeltaEvent(
                delta=pydantic_ai.ThinkingPartDelta(content_delta=text)
            ) if text:
                on_think(text)
            case pydantic_ai.FunctionToolCallEvent(part=part):
                on_tool(part.tool_name)

    def _get_chat_title(
        self, ctx: pydantic_ai.RunContext[Deps]
    ) -> str:
        chat = ctx.deps.doc.chat(ctx.deps.chat_id)
        if chat is None or not chat.title:
            return (
                "Chat title is empty. Before you finish the first turn, call"
                "set_chat_title to update the chat topic."
            )
        return f'Chat title is "{chat.title!r}".'
