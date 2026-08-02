"""Document: single source of truth for a document and its chats.

Owns the mutable Store of immutable value objects, the reentrant lock and
the dirty flag. Reads go through the getters (which return immutable
snapshots); writes go through an Editor from edit(origin). See the package
docstring for the full flow.
"""
import threading
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Callable, Generator
from .change import Change
from .data import (
    ChatCard, ChatCardAction, ChatData, ChatItem, ChatReply, ChatThinking,
    ChatTurn, RouteData, TrackPoint,
)
from .editor import Editor, Origin
from .store import Store


Listener = Callable[[Change, Origin], None]


class Document:
    def __init__(self) -> None:
        self._store = Store()
        self._lock = threading.RLock()
        self._depth = 0
        self._pending: list[tuple[Change, Origin]] = []
        self._listeners: list[Listener] = []
        self._has_edits = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Document":
        doc = cls()
        s = doc._store
        s.title = d.get("title", "")
        s.notes = d.get("notes", "")
        for r in d.get("routes", []):
            track = tuple(TrackPoint(**p) for p in r.get("track", []))
            s.put_route(RouteData(
                id=r.get("id", RouteData.unique_id()),
                title=r.get("title", ""),
                notes=r.get("notes", ""),
                track=track,
            ))
        for c in d.get("chats", []):
            turns = list[ChatTurn]()
            for t in c.get("turns", []):
                items = list[ChatItem]()
                for raw in t.get("items", []):
                    k = raw.get("kind", "")
                    if k == "thinking":
                        items.append(ChatThinking(text=raw.get("text", "")))
                    elif k == "reply":
                        items.append(ChatReply(text=raw.get("text", "")))
                    elif k == "card":
                        items.append(ChatCard(
                            card_kind=raw.get("card_kind", "message"),
                            title=raw.get("title", ""),
                            text=raw.get("text", ""),
                            actions=tuple(
                                ChatCardAction(
                                    id=a["id"],
                                    label=a.get("label", ""),
                                    appearance=a.get("appearance", "secondary"),
                                )
                                for a in raw.get("actions", [])
                            )
                        ))
                turns.append(ChatTurn(
                    id=t.get("id", ChatTurn.unique_id()),
                    prompt=t.get("prompt", ""),
                    items=tuple(items),
                ))
            s.put_chat(ChatData(
                id=c.get("id", ChatData.unique_id()),
                title=c.get("title", "New chat"),
                turns=tuple(turns)
            ))
        doc._has_edits = False
        return doc

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            routes = [
                {
                    "id":    r.id,
                    "title": r.title,
                    "notes": r.notes,
                    "track": [asdict(p) for p in r.track],
                }
                for r in self._store.routes()
            ]
            chats = [
                {
                    "id": c.id,
                    "title": c.title,
                    "turns": [
                        {
                            "id": t.id,
                            "prompt": t.prompt,
                            "items": [asdict(it) for it in t.items],
                        }
                        for t in c.turns
                    ],
                }
                for c in self._store.chats()
            ]
            return {
                "title": self._store.title,
                "notes": self._store.notes,
                "routes": routes,
                "chats": chats,
            }

    @property
    def doc_id(self) -> str:
        return self._store.doc_id

    @property
    def has_edits(self) -> bool:
        with self._lock:
            return self._has_edits

    @property
    def title(self) -> str:
        with self._lock:
            return self._store.title

    @property
    def notes(self) -> str:
        with self._lock:
            return self._store.notes

    def route(self, route_id: str) -> RouteData | None:
        with self._lock:
            return self._store.route(route_id)

    def routes(self) -> tuple[RouteData, ...]:
        with self._lock:
            return tuple(self._store.routes())

    def route_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(r.id for r in self._store.routes())

    def chat(self, chat_id: str) -> ChatData | None:
        with self._lock:
            return self._store.chat(chat_id)

    def chats(self) -> tuple[ChatData, ...]:
        with self._lock:
            return tuple(self._store.chats())

    @contextmanager
    def lock(self) -> Generator[None]:
        """Hold the lock across several reads for a consistent snapshot.

        Read only; for writes use edit().
        """
        with self._lock:
            yield

    def edit(self, origin: Origin) -> Editor:
        """Open an editor - the only way to modify the document.

        Use it as a context manager and apply changes inside the block:

            with doc.edit(origin) as ed:
                ed.apply(SetRouteInfo(route_id, title="Day 2"))

        Entering acquires the document lock; every applied change mutates
        the state immediately (so later reads in the same block see it)
        and is buffered. On a clean exit the buffered changes are delivered to
        subscribers, in order, then the lock is released; if the block raises,
        no notifications are sent. Nested edit() blocks on the same thread
        coalesce into a single flush at the outermost exit.

        origin identifies who is making the edit. It is passed through untouched
        to subscribers so a view can skip echoing a change back onto the widget
        that caused it. Only its identity is used: a UI widget passes self, a
        service passes its own instance. Do slow work (parsing, network, model
        calls) before opening the editor, not inside the block.
        """
        return Editor(self, origin)

    def subscribe(self, listener: Listener) -> None:
        """Register a listener notified after each committed change.

        The listener is called as listener(change, origin) once per buffered
        change, in the order the changes were applied, after the transaction
        commits and the lock has been released. It is not called for changes in
        a block that raised.

        Listeners must be non-blocking and must treat origin as an opaque token
        (compare by identity, never dereference it). They may read the document
        freely, but must not open an editor from within a notification. Typical
        listeners are the controller and the views, which translate changes into
        UI updates.
        """
        self._listeners.append(listener)

    def mark_saved(self) -> None:
        with self._lock:
            self._has_edits = False

    def _begin(self) -> None:
        self._lock.acquire()
        self._depth += 1

    def _apply(self, change: Change, origin: Origin) -> None:
        change.apply(self._store)
        self._has_edits = True
        self._pending.append((change, origin))

    def _end(self, aborted: bool) -> None:
        self._depth -= 1
        if self._depth > 0:
            self._lock.release()
            return
        pending = self._pending
        self._pending = []
        self._lock.release()
        if not aborted:
            for change, origin in pending:
                self._notify(change, origin)

    def _notify(self, change: Change, origin: Origin) -> None:
        for fn in self._listeners:
            fn(change, origin)
