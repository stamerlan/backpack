import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from concurrent.futures import Future
    from .js_worker import JsWorker

logger = logging.getLogger(__name__)


@dataclass
class DialogAction:
    title: str
    result: Any = None
    size: str | None = None
    appearance: str | None = None


@dataclass
class RecentItem:
    title: str
    meta: str
    filename: str


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

    def clear_doc(self) -> "Future[Any]":
        return self.js.submit("doc.clear", ())

    def add_trip_card(
        self, card_id: str, title: str = "", notes: str = ""
    ) -> "Future[Any]":
        return self.js.submit("doc.add_trip_card", (card_id, title, notes))

    def add_route_card(
        self, card_id: str, title: str = "", notes: str = ""
    ) -> "Future[Any]":
        return self.js.submit("doc.add_route_card", (card_id, title, notes))
