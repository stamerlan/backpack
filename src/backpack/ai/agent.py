from typing import Callable, TYPE_CHECKING

import pydantic_ai
import pydantic_ai.capabilities

from . import provider
from .deps import Deps
from .errors import AiError

if TYPE_CHECKING:
    from .. import model
    from ..storage import Storage


def _build_history(
    chat: "model.ChatData",
) -> list[pydantic_ai.ModelMessage]:
    """Map persisted chat turns to pydantic-ai message history.

    Each turn yields the user prompt and, when the model produced any reply
    text, a single assistant message with its reply blocks joined. Thinking and
    card items never enter the LLM context.
    """
    from ..model.data import ChatReply

    messages = list[pydantic_ai.ModelMessage]()
    for turn in chat.turns:
        messages.append(
            pydantic_ai.ModelRequest(
                parts=[pydantic_ai.UserPromptPart(content=turn.prompt)]
            )
        )
        reply = "".join(
            it.text for it in turn.items if isinstance(it, ChatReply)
        )
        if reply:
            messages.append(
                pydantic_ai.ModelResponse(
                    parts=[pydantic_ai.TextPart(content=reply)]
                )
            )
    return messages


class Agent:
    def __init__(self, storage: "Storage") -> None:
        self.storage = storage
        self.agent = pydantic_ai.Agent[Deps, str](
            deps_type=Deps,
            capabilities=[
                pydantic_ai.capabilities.Thinking(effort="medium"),
                pydantic_ai.capabilities.WebSearch(),
            ],
        )

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
