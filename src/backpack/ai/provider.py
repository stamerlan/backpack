from dataclasses import dataclass
from typing import TYPE_CHECKING

from google.genai.types import HttpRetryOptions
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.settings import ModelSettings

from .errors import AiError

if TYPE_CHECKING:
    from ..storage import Storage


@dataclass(frozen=True)
class AiModel:
    id: str
    name: str


async def enum_models() -> tuple[AiModel, ...]:
    """Return available model descriptors."""
    return (
        AiModel("google:gemini-3.6-flash", "Gemini 3.6 Flash"),
        AiModel("google:gemini-3.5-flash", "Gemini 3.5 Flash"),
        AiModel("google:gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
        AiModel("google:gemini-3.1-pro-preview-customtools", "Gemini 3.1 Pro"),
    )


async def build_model(
    model_id: str,
    storage: "Storage",
    model_settings: ModelSettings | None = None,
) -> Model:
    """Build a pydantic-ai Model from a model id string.

    Loads the required API key from the OS credential store (async) and
    constructs the provider. No network connection is opened until the model is
    actually used.
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
                raise AiError("No Gemini API key")
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
                        http_status_codes=[408, 429, 500, 502, 503, 504],
                    ),
                ),
            )
        case _:
            raise AiError(f"Unknown provider {provider_name!r}")
