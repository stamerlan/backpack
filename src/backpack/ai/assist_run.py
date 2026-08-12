import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

import pydantic_ai
from pydantic_ai.models import Model

from ..i18n import i18n
from ..model import ChatCard, ChatCardAction, ChatItem, ChatReply, ChatThinking

if TYPE_CHECKING:
    from ..model import ChatData, Document, Poi
    from .agent import Agent


@dataclass
class AssistRun:
    """One in-flight assistant run: its inputs, its stop handle and output.

    An instance is passed to pydantic-ai as the run deps, so tools reach the
    document, POIs and ids through it. It also owns the streaming task, so the
    run can be stopped from another task, and accumulates the produced items,
    coalescing consecutive thinking or reply tokens into one block. On
    completion the agent hands the items back to be committed to the document.
    """

    agent: "Agent"
    doc: "Document"
    poi: "Mapping[str, tuple[Poi, ...]]"
    chat_id: str
    model_id: str
    prompt: str
    model: Model
    on_text: Callable[[str], Any] = lambda text: None
    on_think: Callable[[str], Any] = lambda text: None
    on_tool: Callable[[str], Any] = lambda text: None
    items: list[ChatItem] = field(default_factory=list)
    _task: "asyncio.Task[None] | None" = field(
        default=None, init=False, repr=False
    )

    @staticmethod
    def build_history(
        chat: "ChatData",
    ) -> list[pydantic_ai.ModelMessage]:
        """Map persisted chat turns to pydantic-ai message history.

        Each turn contributes the user prompt and a single assistant message
        with its reply blocks joined. A turn that produced no reply (e.g. a
        failed run) is skipped so the history never carries a dangling user
        message. Thinking and card items never enter the LLM context.
        """
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

    def stop(self) -> None:
        """Request cancellation of this run from another task."""
        if self._task is not None:
            self._task.cancel()

    async def stream(self, chat: "ChatData") -> None:
        """Drive the streamed run, dispatching each event into this run.

        The event loop runs in an owned task so stop() can cancel just this
        run from another task. Awaiting it here surfaces that cancellation as
        asyncio.CancelledError, and any failure, to the caller. An outer
        cancellation tears the owned task down through the finally.
        """
        history = self.build_history(chat)
        self._task = asyncio.ensure_future(self._drive(history))
        try:
            await self._task
        finally:
            self._task.cancel()

    async def _drive(self, history: list[pydantic_ai.ModelMessage]) -> None:
        """Open the streamed run and dispatch each event into this run."""
        async with self.model:
            async with self.agent.agent.run_stream_events(
                self.prompt,
                deps=self,
                model=self.model,
                message_history=history,
            ) as events:
                async for ev in events:
                    self._dispatch_event(ev)

    def _dispatch_event(self, ev: object) -> None:
        match ev:
            case pydantic_ai.PartStartEvent(
                part=pydantic_ai.TextPart(content=text)
            ) if text:
                self.add_reply(text)
            case pydantic_ai.PartDeltaEvent(
                delta=pydantic_ai.TextPartDelta(content_delta=text)
            ) if text:
                self.add_reply(text)
            case pydantic_ai.PartStartEvent(
                part=pydantic_ai.ThinkingPart(content=text)
            ) if text:
                self.add_thinking(text)
            case pydantic_ai.PartDeltaEvent(
                delta=pydantic_ai.ThinkingPartDelta(content_delta=text)
            ) if text:
                self.add_thinking(text)
            case pydantic_ai.FunctionToolCallEvent(part=part):
                self.on_tool(part.tool_name)

    def add_reply(self, text: str) -> None:
        """Append reply text, merging into the trailing reply block."""
        if self.items and isinstance(self.items[-1], ChatReply):
            self.items[-1] = ChatReply(self.items[-1].text + text)
        else:
            self.items.append(ChatReply(text))
        self.on_text(text)

    def add_thinking(self, text: str) -> None:
        """Append thinking text, merging into the trailing thinking block."""
        if self.items and isinstance(self.items[-1], ChatThinking):
            self.items[-1] = ChatThinking(self.items[-1].text + text)
        else:
            self.items.append(ChatThinking(text))
        self.on_think(text)

    def add_error(self, message: str, retryable: bool) -> None:
        """Append an error card, with a retry action when retryable."""
        self.items.append(ChatCard(
            card_kind="error",
            text=message,
            actions=(
                ChatCardAction(
                    id="retry",
                    label=i18n.gettext("Retry"),
                    appearance="primary"
                ),
            ) if retryable else ()
        ))

    def has_reply(self) -> bool:
        """Whether the run produced any reply text."""
        return any(isinstance(it, ChatReply) for it in self.items)
