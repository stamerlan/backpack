from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from .agent import Agent
    from .. import model


@dataclass
class Deps:
    """What the assistant is allowed to touch during a run."""

    agent: "Agent"
    doc: "model.Document"
    poi: "Mapping[str, tuple[model.Poi, ...]]"
    chat_id: str
    model_id: str
