"""The change protocol and the concrete edits to a document.

A Change is both command and event: apply(state) performs the mutation, and the
same object is delivered to subscribers as the description of what happened.
Changes are frozen and build replacement values, so they never mutate a value
object in place. Adding a new kind of edit means adding a dataclass here and a
handler in the views that render it - Document and Editor are untouched, because
Document._apply just calls change.apply.
"""

from dataclasses import dataclass, replace
from typing import Protocol
from .data import ChatData, ChatTurn, RouteData, TrackPoint
from .store import State


class Change(Protocol):
    """A single, self-applying edit to the document state."""

    def apply(self, state: State) -> None: ...


@dataclass(frozen=True, slots=True)
class SetDocInfo:
    title: str | None = None
    notes: str | None = None

    def apply(self, state: State) -> None:
        if self.title is not None:
            state.title = self.title
        if self.notes is not None:
            state.notes = self.notes


@dataclass(frozen=True, slots=True)
class AddRoute:
    route: RouteData

    def apply(self, state: State) -> None:
        state.put_route(self.route)


@dataclass(frozen=True, slots=True)
class RemoveRoute:
    route_id: str

    def apply(self, state: State) -> None:
        state.del_route(self.route_id)


@dataclass(frozen=True, slots=True)
class MoveRoute:
    route_id: str
    after_id: str | None

    def apply(self, state: State) -> None:
        state.move_route(self.route_id, self.after_id)


@dataclass(frozen=True, slots=True)
class SetRouteInfo:
    route_id: str
    title: str | None = None
    notes: str | None = None

    def apply(self, state: State) -> None:
        r = state.route(self.route_id)
        if r is None:
            return
        state.put_route(replace(r,
            title=r.title if self.title is None else self.title,
            notes=r.notes if self.notes is None else self.notes,
        ))


@dataclass(frozen=True, slots=True)
class SetRouteTrack:
    route_id: str
    track: tuple[TrackPoint, ...]

    def apply(self, state: State) -> None:
        r = state.route(self.route_id)
        if r is not None:
            state.put_route(replace(r, track=self.track))


@dataclass(frozen=True, slots=True)
class AddChat:
    chat: ChatData

    def apply(self, state: State) -> None:
        state.put_chat(self.chat)


@dataclass(frozen=True, slots=True)
class RemoveChat:
    chat_id: str

    def apply(self, state: State) -> None:
        state.del_chat(self.chat_id)


@dataclass(frozen=True, slots=True)
class SetChatTitle:
    chat_id: str
    title: str

    def apply(self, state: State) -> None:
        c = state.chat(self.chat_id)
        if c is not None:
            state.put_chat(replace(c, title=self.title))


@dataclass(frozen=True, slots=True)
class AppendChatTurn:
    chat_id: str
    turn: ChatTurn

    def apply(self, state: State) -> None:
        c = state.chat(self.chat_id)
        if c is not None:
            state.put_chat(replace(c, turns=c.turns + (self.turn,)))


@dataclass(frozen=True, slots=True)
class RemoveChatTurn:
    """Drop the turn with the given id from a chat.

    Used to retry a turn: the failed turn is removed and a fresh run
    appends a new turn on top of the remaining history.
    """

    chat_id: str
    turn_id: str

    def apply(self, state: State) -> None:
        c = state.chat(self.chat_id)
        if c is None:
            return
        turns = tuple(t for t in c.turns if t.id != self.turn_id)
        if len(turns) != len(c.turns):
            state.put_chat(replace(c, turns=turns))
