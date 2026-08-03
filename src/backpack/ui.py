import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Literal

if TYPE_CHECKING:
    from concurrent.futures import Future
    from .js_worker import JsWorker
    from .model.data import TrackPoint
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


class UI:
    """Outbound bridge: methods Python may call on the frontend."""

    def __init__(self, js: "JsWorker") -> None:
        self.js = js

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
