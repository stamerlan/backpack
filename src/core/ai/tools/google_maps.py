import logging

from google import genai
from google.genai import errors, types
from pydantic_ai import RunContext

from ... import route
from .. import prompts
from ..assist_run import AssistRun

logger = logging.getLogger(__name__)


def google_maps(ctx: RunContext[AssistRun], query: str) -> str:
    """Ask about real-world places near the trip via Google Maps.

    Use for huts, shelters, water, shops, campsites, viewpoints, opening hours,
    access and whether a place still exists. Pass a natural language query.
    Returns a plain-text grounded answer.
    """
    model_id = ctx.deps.model_id
    provider_name, _, model_name = model_id.partition(":")
    if provider_name != "google":
        return "Maps grounding is Gemini-only"
    api_key = ctx.deps.agent.storage.vault.get("gemini_api_key")
    if not api_key:
        return "Map lookup failed, no Gemini API key."

    try:
        with ctx.deps.doc.lock():
            south, west, north, east = route.bbox(
                (p.lat, p.long)
                for r in ctx.deps.doc.routes()
                for p in r.track
            )
        retrieval_config = types.RetrievalConfig(
            lat_lng=types.LatLng(
                latitude=(south + north) / 2,
                longitude=(west + east) / 2,
            ),
        )
    except ValueError:
        retrieval_config = None

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=180_000,
                retry_options=types.HttpRetryOptions(
                    attempts=5,
                    initial_delay=1.0,
                    max_delay=30.0,
                    exp_base=2.0,
                    jitter=1.0,
                ),
            ),
        )
        resp = client.models.generate_content(
            model=model_name,
            contents=query,
            config=types.GenerateContentConfig(
                system_instruction=prompts.MAPS,
                tools=[types.Tool(google_maps=types.GoogleMaps())],
                tool_config=types.ToolConfig(
                    retrieval_config=retrieval_config,
                    include_server_side_tool_invocations=True,
                ),
            ),
        )
    except errors.APIError as e:
        logger.error(e)
        return "Map lookup failed, tell the user to try again."
    return resp.text or "No map information found."
