import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Literal

if TYPE_CHECKING:
    from concurrent.futures import Future
    from .ai import AiModel
    from .js_worker import JsWorker
    from .model.data import ChatCard, TrackPoint
    from .route import RouteStats

logger = logging.getLogger(__name__)


@dataclass
class DialogAction:
    title: str
    result: Any = None
    size: Literal["small", "medium", "large"] | None = None
    appearance: (
        Literal["secondary", "primary", "outline", "subtle", "transparent"]
        | None
    ) = None


@dataclass
class RecentItem:
    title: str
    meta: str
    filename: str


@dataclass
class NotifyAction:
    title: str
    result: Any = None
    appearance: (
        Literal["secondary", "primary", "outline", "subtle", "transparent"]
        | None
    ) = None


class Assist:
    """Outbound bridge for the assistant panel (window.assist.*)."""

    def __init__(self, js: "JsWorker") -> None:
        self.js = js

    def clear(self) -> "Future[Any]":
        return self.js.submit("assist.clear", ())

    def set_models(self, models: Iterable["AiModel"]) -> "Future[Any]":
        return self.js.submit("assist.set_models", (list(models),))

    def new_chat(self, chat_id: str, title: str = "") -> "Future[Any]":
        return self.js.submit("assist.new_chat", (chat_id, title))

    def del_chat(self, chat_id: str) -> "Future[Any]":
        return self.js.submit("assist.del_chat", (chat_id,))

    def set_active_chat(self, chat_id: str) -> "Future[Any]":
        return self.js.submit("assist.set_active_chat", (chat_id,))

    def set_chat_title(self, chat_id: str, title: str) -> "Future[Any]":
        return self.js.submit("assist.set_chat_title", (chat_id, title))

    def new_turn(
        self, chat_id: str, turn_id: str, prompt: str
    ) -> "Future[Any]":
        return self.js.submit("assist.new_turn", (chat_id, turn_id, prompt))

    def del_turn(self, chat_id: str, turn_id: str) -> "Future[Any]":
        return self.js.submit("assist.del_turn", (chat_id, turn_id))

    def append_thinking(self, chat_id: str, text: str) -> "Future[Any]":
        return self.js.submit("assist.append_thinking", (chat_id, text))

    def append_reply(self, chat_id: str, text: str) -> "Future[Any]":
        return self.js.submit("assist.append_reply", (chat_id, text))

    def add_card(self, chat_id: str, card: "ChatCard") -> "Future[Any]":
        return self.js.submit("assist.add_card", (chat_id, card))

    def end_turn(self, chat_id: str) -> "Future[Any]":
        return self.js.submit("assist.end_turn", (chat_id,))


class UI:
    """Outbound bridge: methods Python may call on the frontend."""

    def __init__(self, js: "JsWorker") -> None:
        self.js = js
        self.assist = Assist(js)

    def show_dialog(
        self, title: str, text: str, actions: Iterable[DialogAction] = ()
    ) -> "Future[Any]":
        return self.js.submit("show_dialog", (title, text, list(actions)))

    def set_recent(self, items: Iterable[RecentItem]) -> "Future[Any]":
        return self.js.submit("menu.set_recent", (list(items),))

    def notify(
        self,
        message: str,
        intent: Literal["info", "success", "warning", "error"] = "info",
        title: str = "",
        actions: Iterable[NotifyAction] = (),
    ) -> "Future[Any]":
        return self.js.submit(
            "notify", (message, intent, title, list(actions))
        )

    def clear_notify(self) -> "Future[Any]":
        return self.js.submit("clear_notify", ())

    def set_busy(self, busy: bool, label: str = "") -> "Future[Any]":
        return self.js.submit("set_busy", (busy, label))

    def clear_doc(self) -> "Future[Any]":
        return self.js.submit("doc.clear", ())

    def add_trip_card(
        self, card_id: str, title: str = "", notes: str = ""
    ) -> "Future[Any]":
        return self.js.submit("doc.add_trip_card", (card_id, title, notes))

    def set_trip_card(self, title: str, notes: str) -> "Future[Any]":
        return self.js.submit("doc.set_trip_card", (title, notes))

    def set_route_card(
        self, route_id: str, title: str, notes: str
    ) -> "Future[Any]":
        return self.js.submit(
            "doc.set_route_card", (route_id, title, notes)
        )

    def set_route_loading(self, route_id: str, loading: bool) -> "Future[Any]":
        """Show or hide the route header spinner while details load."""
        return self.js.submit("doc.set_route_loading", (route_id, loading))

    def add_route_card(
        self, card_id: str, title: str, notes: str,
        track: "Iterable[TrackPoint]", stats: "RouteStats | None"
    ) -> "Future[Any]":
        return self.js.submit(
            "doc.add_route_card", (card_id, title, notes, list(track), stats)
        )

    def remove_card(self, card_id: str) -> "Future[Any]":
        return self.js.submit("doc.remove_card", (card_id,))

    def move_card(
        self, card_id: str, after_id: str | None
    ) -> "Future[Any]":
        return self.js.submit("doc.move_card", (card_id, after_id))
