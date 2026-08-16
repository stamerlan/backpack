import logging
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

import pydantic_ai
import pydantic_ai.capabilities
from babel import Locale
from google.genai.types import HttpRetryOptions
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from . import prompts, tools
from .errors import AiError
from .assist_run import AssistRun
from ..i18n import i18n

if TYPE_CHECKING:
    from collections.abc import Mapping
    from .. import model
    from ..nominatim import Nominatim
    from ..storage import Storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiModel:
    id: str
    name: str


class Agent:
    @staticmethod
    async def enum_models() -> tuple[AiModel, ...]:
        """Return available model descriptors."""
        return (
            AiModel("google:gemini-3.7-flash", "Gemini 3.7 Flash"),
            AiModel("google:gemini-3.6-flash", "Gemini 3.6 Flash"),
            AiModel("google:gemini-3.5-flash", "Gemini 3.5 Flash"),
            AiModel("google:gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
            AiModel(
                "google:gemini-3.1-pro-preview-customtools", "Gemini 3.1 Pro"
            ),
        )

    @staticmethod
    async def build_model(
        model_id: str,
        storage: "Storage",
        model_settings: ModelSettings | None = None,
    ) -> Model:
        """Build a pydantic-ai Model from a model id string.

        Loads the required API key from the OS credential store (async) and
        constructs the provider. No network connection is opened until the
        model is actually used.
        """
        if model_settings is None:
            model_settings = ModelSettings(timeout=180.0)
        provider_name, _, name = model_id.partition(":")

        match provider_name:
            case "google":
                api_key = storage.vault.get("gemini_api_key")
                if not api_key:
                    api_key = await storage.load_key("gemini_api_key")
                if not api_key:
                    raise AiError(i18n.gettext("No Gemini API key"))
                return GoogleModel(
                    name,
                    settings=model_settings,
                    provider=GoogleProvider(
                        api_key=api_key,
                        retry_options=HttpRetryOptions(
                            attempts=5,
                            initial_delay=1.0,
                            max_delay=30.0,
                            exp_base=2.0,
                            http_status_codes=[408, 429, 500, 502, 503, 504]
                        ),
                    ),
                )
            case _:
                raise AiError(f"Unknown provider {provider_name!r}")

    def __init__(self, storage: "Storage", nominatim: "Nominatim") -> None:
        self.storage = storage
        self.nominatim = nominatim
        self._runs: dict[str, AssistRun] = {}
        self.agent = pydantic_ai.Agent[AssistRun, str](
            deps_type=AssistRun,
            instructions=prompts.SYSTEM,
            capabilities=[
                pydantic_ai.capabilities.Thinking(effort="medium"),
                pydantic_ai.capabilities.WebSearch(),
            ],
        )

        self.agent.instructions(self._get_locale)
        self.agent.instructions(self._get_chat_title)
        self.agent.tool(tools.geocode)
        self.agent.tool(tools.get_poi)
        self.agent.tool(tools.get_trip_info)
        self.agent.tool(tools.google_maps)
        self.agent.tool(tools.reverse_geocode)
        self.agent.tool(tools.set_chat_title)
        self.agent.tool(tools.set_route_info)
        self.agent.tool(tools.set_trip_info)

    async def ask(
        self,
        doc: "model.Document",
        poi: "Mapping[str, tuple[model.Poi, ...]]",
        chat_id: str,
        model_id: str,
        prompt: str,
        on_text: Callable[[str], Any] = lambda text: None,
        on_think: Callable[[str], Any] = lambda text: None,
        on_tool: Callable[[str], Any] = lambda text: None,
    ) -> "tuple[model.ChatItem, ...]":
        """Run one assistant turn and return the items it produced.

        Reply and thinking tokens are streamed live through the callbacks and
        also accumulated into the returned items, which the caller commits to
        the document. A model failure is turned into a trailing error card, so
        a returned list always describes a finished turn. Stopping the run (see
        stop) instead raises asyncio.CancelledError so the caller can drop it.

        on_tool is called with the tool function name each time the model
        invokes a tool, so the caller can emit a status card.
        """
        logger.debug(f"chat_id:{chat_id} model_id:{model_id!r}")
        llm = await self.build_model(model_id, self.storage)
        if (chat := doc.chat(chat_id)) is None:
            raise AiError(f"No chat id:{chat_id}")

        # Register the run so stop() can cancel it. Only one run per chat is
        # expected, but cancel any earlier one to stay safe.
        run = AssistRun(self, doc, poi, chat_id, model_id, prompt, llm,
            on_text=on_text, on_think=on_think, on_tool=on_tool,
        )
        if (prev := self._runs.get(chat_id)) is not None:
            prev.stop()
        self._runs[chat_id] = run

        try:
            await run.stream(chat)
            if not run.has_reply():
                raise AiError("The model returned an empty reply.", True)
        except AiError as e:
            logger.exception(e.message)
            run.add_error(e.message, e.retryable)
        except Exception as e:
            logger.exception("assist run failed")
            err = AiError.convert(e)
            run.add_error(err.message, err.retryable)
        finally:
            if self._runs.get(chat_id) is run:
                del self._runs[chat_id]

        return tuple(run.items)

    def stop(self, chat_id: str) -> None:
        """Stop the in-flight run for a chat, if one is running."""
        logger.debug(f"chat_id:{chat_id}")
        if (run := self._runs.get(chat_id)) is not None:
            run.stop()

    def _get_locale(self, ctx: pydantic_ai.RunContext[AssistRun]) -> str:
        language = Locale(i18n.lang).get_display_name("en") or i18n.lang
        if i18n.units == "imperial":
            units = "imperial units (miles, feet, pounds, ounces)"
        else:
            units = "metric units (kilometers, meters, kilograms, grams)"
        return (
            f"Write all user-facing text (titles, notes and replies) in "
            f"{language}. Express every quantity in {units}, converting "
            f"figures from web searches or other sources into them."
        )

    def _get_chat_title(self, ctx: pydantic_ai.RunContext[AssistRun]) -> str:
        chat = ctx.deps.doc.chat(ctx.deps.chat_id)
        if chat is None or not chat.title:
            return (
                "Chat title is empty. Before you finish the first turn, call"
                "set_chat_title to update the chat topic."
            )
        return f'Chat title is "{chat.title!r}".'
