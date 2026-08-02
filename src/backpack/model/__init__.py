"""Document model: the single source of truth for a document and its chats.

This subpackage owns all persistent state of a document (its routes) together
with the assistant chats, and it is the only place allowed to change that state.
Everything outside (the controller, the views and the import and assistant
services) either reads immutable snapshots from here or asks the document to
apply a change. The model itself knows nothing about the UI, the network or the
assistant.

Modules
-------
data.py
    Frozen value objects: TrackPoint, RouteData, the chat reply items
    (ChatThinking, ChatReply, ChatCard with ChatCardAction, united by the
    ChatItem alias), ChatTurn (a prompt plus its reply items) and ChatData.
    These carry state only, never behavior, and are immutable, so they can
    be shared freely without defensive copies.
store.py
    The State protocol (the narrow mutation surface a Change may touch) and
    Store, the ordered container of RouteData plus the chats and the document
    level title and notes.
change.py
    The Change protocol and the concrete changes (AddRoute, SetRouteInfo,
    SetRouteTrack, AppendChatTurn, ...). A Change knows only how to apply
    itself to a State; it is also the payload delivered to subscribers.
editor.py
    The Editor handle returned by Document.edit(origin). It binds the origin of
    an edit, holds the lock for its scope, buffers changes and flushes their
    notifications on commit.
document.py
    Document: owns the Store, the reentrant lock and the dirty flag, exposes
    read only getters, the edit() factory and subscribe(), and handles
    serialization to and from JSON.

Why this design
---------------
State and behavior are split on purpose. Because the value objects are immutable
and only the document holds them, no code can change document data behind the
model's back; a stray write raises instead of silently losing a notification.
That single rule makes three guarantees trustworthy:

- Dirty tracking is centralized: every edit flows through one apply path.
- Thread safety is centralized: the editor scope takes one reentrant lock, so
  the UI thread and the assistant worker can all write without racing.
- The view stays decoupled: the document emits abstract, origin tagged change
  events and never calls the UI, so the model is testable on its own and new
  writers get view updates for free.

Performing an edit
------------------
All writes go through an editor obtained with an origin (any object; e.g. UI
view passes self, a service passes itself). Reads use the document getters
directly and need no editor.

    with doc.edit(origin) as ed:
        ed.apply(SetRouteInfo(route_id, title="Day 2"))
        ed.apply(SetRouteTrack(route_id, track))

The flow of a single edit:

1. edit(origin) acquires the reentrant lock and returns an Editor bound to that
   origin.
2. ed.apply(change) calls change.apply(store) to mutate the state (by replacing
   an immutable value), marks the document dirty and buffers the change.
3. On leaving the with block the buffered changes are dispatched, in order, to
   every subscriber as (change, origin), then the lock is released. If the block
   raises, no notifications are sent.
4. Subscribers (the controller and views) react to the change and update the UI,
   skipping any change whose origin is the widget that caused it to avoid
   echoing a value back onto the source.

Do slow work (GPX parsing, network, model calls) outside the editor scope;
compute the new value first, then open an editor only to commit it.

Adding new data or a new modification
-------------------------------------
To add a modifiable field or a new kind of edit:

1. Add the field to the relevant frozen value object in data.py.
2. If the change needs a storage operation the State does not yet offer, add it
   to the State protocol and to Store in store.py. Most edits reuse put_route or
   put_chat and skip this step.
3. Add a frozen Change dataclass in change.py implementing apply(state),
   building the replacement value with dataclasses.replace.
4. Register a handler for the new change type in each view that renders it (the
   subscriber dispatch ignores change types it does not handle).

You do not touch Document, Editor or the apply path: Document._apply is
polymorphic (it just calls change.apply) and Editor.apply is generic, so a new
change type is confined to its dataclass and the views that show it.
"""

from .document import Document
from .editor import Editor, Origin
from .data import (
    ChatCard, ChatCardAction, ChatData, ChatItem, ChatReply, ChatThinking,
    ChatTurn, RouteData, TrackPoint,
)
from .change import (
    AddChat,
    AddRoute,
    AppendChatTurn,
    Change,
    MoveRoute,
    RemoveChat,
    RemoveChatTurn,
    RemoveRoute,
    SetChatTitle,
    SetDocInfo,
    SetRouteInfo,
    SetRouteTrack,
)

__all__ = [
    "AddChat",
    "AddRoute",
    "AppendChatTurn",
    "Change",
    "ChatCard",
    "ChatCardAction",
    "ChatData",
    "ChatItem",
    "ChatReply",
    "ChatThinking",
    "ChatTurn",
    "Document",
    "Editor",
    "MoveRoute",
    "Origin",
    "RemoveChat",
    "RemoveChatTurn",
    "RemoveRoute",
    "RouteData",
    "SetChatTitle",
    "SetDocInfo",
    "SetRouteInfo",
    "SetRouteTrack",
    "TrackPoint",
]
