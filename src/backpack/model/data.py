"""Immutable value objects that make up a document.

These carry state only, never behavior. They are frozen so that once the
document hands one out it cannot be mutated behind the model's back; a change is
made by building a new value with dataclasses.replace and committing it through
an editor. Being immutable, they are also safe to share from getters without
defensive copies.
"""
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class TrackPoint:
    """A single sampled point along a route track."""

    lat: float
    long: float
    elev_m: float
    slope: float
    dist_m: float   # distance from route start including elevation, meters
    dur_s: float    # estimated time arrival, seconds


@dataclass(frozen=True, slots=True)
class Poi:
    """A point of interest found near the track.

    tags holds the raw OSM tags. The dataclass is frozen but the dict is not;
    treat tags as read only.
    """

    lat: float
    long: float
    ofs_m: float            # distance from the track in meters
    tags: dict[str, str]    # raw OSM tags; treat as read-only


@dataclass(frozen=True, slots=True)
class RouteData:
    """One route: its description, its sampled track and its POIs.

    poi is None while it has not been loaded yet (fetched lazily after the
    track); an empty tuple means loaded but nothing was found near the route.
    """

    @staticmethod
    def unique_id() -> str: return f"route-{uuid4().hex}"

    id: str = field(default_factory=unique_id)
    title: str = ""
    notes: str = ""
    track: tuple[TrackPoint, ...] = ()
    poi: tuple[Poi, ...] | None = None


@dataclass(frozen=True, slots=True)
class ChatCardAction:
    """A button rendered inside a ChatCard."""

    id: str
    label: str
    appearance: Literal[
        "primary", "secondary", "subtle"
    ] = "secondary"


@dataclass(frozen=True, slots=True)
class ChatThinking:
    """A thinking stream block produced by the model."""

    text: str
    kind: Literal["thinking"] = "thinking"


@dataclass(frozen=True, slots=True)
class ChatReply:
    """A reply stream block produced by the model."""

    text: str
    kind: Literal["reply"] = "reply"


@dataclass(frozen=True, slots=True)
class ChatCard:
    """Structured block: error, message, suggestion or input."""

    card_kind: Literal["error", "message", "suggest", "input"]
    title: str = ""
    text: str = ""
    actions: tuple[ChatCardAction, ...] = ()
    kind: Literal["card"] = "card"


ChatItem = ChatThinking | ChatReply | ChatCard


@dataclass(frozen=True, slots=True)
class ChatTurn:
    """One exchange: the user prompt and the items it produced.

    A turn always begins with a prompt, so the prompt is a plain field
    rather than an item. items holds only what the model produced in
    response - thinking, reply and card blocks, in order.
    """

    @staticmethod
    def unique_id() -> str:  return f"turn-{uuid4().hex}"

    id: str = field(default_factory=unique_id)
    prompt: str = ""
    items: tuple[ChatItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ChatData:
    """An assistant conversation: a title and its ordered turns."""

    @staticmethod
    def unique_id() -> str:  return f"chat-{uuid4().hex}"

    id: str = field(default_factory=unique_id)
    title: str = "New chat"
    turns: tuple[ChatTurn, ...] = ()
