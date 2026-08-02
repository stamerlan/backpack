"""The mutable container behind the document and its access contract.

State is the narrow surface a Change is allowed to touch, so changes stay
decoupled from how the data is actually stored (and can be tested against a
fake). Store is the concrete implementation: an ordered map of routes, a map of
chats and the document level title and notes. It holds immutable value objects
and is only ever mutated by the document, under the lock, via changes.
"""
from typing import Iterable, Protocol
from uuid import uuid4
from .data import RouteData, ChatData


class State(Protocol):
    """Mutation and lookup surface a Change may use."""

    doc_id: str
    title: str
    notes: str

    def route(self, route_id: str) -> RouteData | None: ...
    def routes(self) -> Iterable[RouteData]: ...
    def put_route(self, route: RouteData) -> None: ...
    def del_route(self, route_id: str) -> None: ...
    def move_route(self, route_id: str, after_id: str | None) -> None: ...

    def chat(self, chat_id: str) -> ChatData | None: ...
    def chats(self) -> Iterable[ChatData]: ...
    def put_chat(self, chat: ChatData) -> None: ...
    def del_chat(self, chat_id: str) -> None: ...


class Store:
    """In-memory State backed by insertion-ordered dicts."""

    def __init__(self) -> None:
        self.doc_id = f"doc-{uuid4().hex}"
        self.title = ""
        self.notes = ""
        self._routes: dict[str, RouteData] = {}
        self._chats: dict[str, ChatData] = {}

    def route(self, route_id: str) -> RouteData | None:
        return self._routes.get(route_id)

    def routes(self) -> Iterable[RouteData]:
        return tuple(self._routes.values())

    def put_route(self, route: RouteData) -> None:
        """Insert or replace a route.

        Replacing an existing id keeps its position; a new id is appended. This
        is what lets a field edit leave route order untouched.
        """
        self._routes[route.id] = route

    def del_route(self, route_id: str) -> None:
        self._routes.pop(route_id, None)

    def move_route(self, route_id: str, after_id: str | None) -> None:
        """Reorder route_id to sit just after after_id.

        after_id None moves it to the front. Unknown ids or a no-op move are
        ignored rather than raising, so a stale drag cannot abort a transaction
        mid-commit.
        """
        if route_id not in self._routes or route_id == after_id:
            return
        if after_id is not None and after_id not in self._routes:
            return
        route = self._routes.pop(route_id)
        new: dict[str, RouteData] = {}
        if after_id is None:          # nothing precedes: goes first
            new[route_id] = route
        for rid, r in self._routes.items():
            new[rid] = r
            if rid == after_id:       # insert moved route after after_id
                new[route_id] = route
        self._routes = new

    def chat(self, chat_id: str) -> ChatData | None:
        return self._chats.get(chat_id)

    def chats(self) -> Iterable[ChatData]:
        return tuple(self._chats.values())

    def put_chat(self, chat: ChatData) -> None:
        self._chats[chat.id] = chat

    def del_chat(self, chat_id: str) -> None:
        self._chats.pop(chat_id, None)
