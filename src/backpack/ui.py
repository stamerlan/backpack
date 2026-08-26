import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, Literal

if TYPE_CHECKING:
    from concurrent.futures import Future
    from .ai import AiModel
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

    def __init__(
        self, exec_script: Callable[[str, tuple[Any, ...]], "Future[Any]"]
    ) -> None:
        self._exec_script = exec_script

    def clear(self) -> "Future[Any]":
        return self._exec_script("assist.clear", ())

    def set_models(self, models: Iterable["AiModel"]) -> "Future[Any]":
        return self._exec_script("assist.set_models", (list(models),))

    def get_model(self, chat_id: str) -> "Future[Any]":
        """Resolve to the chat's currently selected model id."""
        return self._exec_script("assist.get_model", (chat_id,))

    def new_chat(self, chat_id: str, title: str = "") -> "Future[Any]":
        return self._exec_script("assist.new_chat", (chat_id, title))

    def del_chat(self, chat_id: str) -> "Future[Any]":
        return self._exec_script("assist.del_chat", (chat_id,))

    def set_active_chat(self, chat_id: str) -> "Future[Any]":
        return self._exec_script("assist.set_active_chat", (chat_id,))

    def set_chat_title(self, chat_id: str, title: str) -> "Future[Any]":
        return self._exec_script("assist.set_chat_title", (chat_id, title))

    def new_turn(
        self, chat_id: str, turn_id: str, prompt: str
    ) -> "Future[Any]":
        return self._exec_script("assist.new_turn", (chat_id, turn_id, prompt))

    def del_turn(self, chat_id: str, turn_id: str) -> "Future[Any]":
        return self._exec_script("assist.del_turn", (chat_id, turn_id))

    def append_thinking(self, chat_id: str, text: str) -> "Future[Any]":
        return self._exec_script("assist.append_thinking", (chat_id, text))

    def append_reply(self, chat_id: str, text: str) -> "Future[Any]":
        return self._exec_script("assist.append_reply", (chat_id, text))

    def add_card(self, chat_id: str, card: "ChatCard") -> "Future[Any]":
        return self._exec_script("assist.add_card", (chat_id, card))

    def end_turn(self, chat_id: str) -> "Future[Any]":
        return self._exec_script("assist.end_turn", (chat_id,))

    def mark_read(self, chat_ids: str | Iterable[str]) -> "Future[Any]":
        ids = [chat_ids] if isinstance(chat_ids, str) else list(chat_ids)
        return self._exec_script("assist.mark_read", (ids,))


class UI:
    """Outbound bridge: methods Python may call on the frontend."""

    def __init__(
        self, exec_script: Callable[[str, tuple[Any, ...]], "Future[Any]"]
    ) -> None:
        self._exec_script = exec_script
        self.assist = Assist(exec_script)

    def show_dialog(
        self, title: str, text: str, actions: Iterable[DialogAction] = ()
    ) -> "Future[Any]":
        return self._exec_script("show_dialog", (title, text, list(actions)))

    def set_theme(self, mode: str) -> "Future[Any]":
        """Apply a theme mode to the window.
        
        :param str mode: "light", "dark" or "system" to follow system settings.
        """
        return self._exec_script("set_theme_mode", (mode,))

    def set_locale(self, tag: str, units: str) -> "Future[Any]":
        """Apply the active locale and units to the frontend.

        Mirrors set_theme: this is the single place the locale is pushed, so
        the frontend can switch its catalog and seed its units state on startup
        and after a language change.

        :param str tag: BCP-47 tag of the active locale, e.g. "en-US" or "ru".
        :param str units: measurement system, "metric" or "imperial".
        """
        return self._exec_script("set_locale", (tag, units))

    def show_settings_dialog(self, settings: dict[str, Any]) -> "Future[Any]":
        """Open the settings dialog, resolving to the edited values or None.

        The frontend fills each control from ``settings`` and returns a dict of
        the same keys on save, or None when the dialog is dismissed.
        """
        return self._exec_script("show_settings_dialog", (settings,))

    def set_recent(self, items: Iterable[RecentItem]) -> "Future[Any]":
        return self._exec_script("menu.set_recent", (list(items),))

    def set_doc_state(self, filename: str | None, dirty: bool) -> "Future[Any]":
        """Tell the app bar which file is open and whether it has edits.

        :param filename: the open file's base name, or None for a trip that has
            not been saved to a file yet.
        :param dirty: whether the document has unsaved changes.
        """
        return self._exec_script("set_doc_state", (filename, dirty))

    def notify(
        self,
        message: str,
        intent: Literal["info", "success", "warning", "error"] = "info",
        title: str = "",
        actions: Iterable[NotifyAction] = (),
    ) -> "Future[Any]":
        return self._exec_script(
            "notify", (message, intent, title, list(actions))
        )

    def clear_notify(self) -> "Future[Any]":
        return self._exec_script("clear_notify", ())

    def set_busy(self, busy: bool, label: str = "") -> "Future[Any]":
        return self._exec_script("set_busy", (busy, label))

    def clear_doc(self) -> "Future[Any]":
        return self._exec_script("doc.clear", ())

    def add_trip_card(
        self, card_id: str, title: str = "", notes: str = ""
    ) -> "Future[Any]":
        return self._exec_script("doc.add_trip_card", (card_id, title, notes))

    def set_trip_card(self, title: str, notes: str) -> "Future[Any]":
        return self._exec_script("doc.set_trip_card", (title, notes))

    def set_route_card(
        self, route_id: str, title: str, notes: str
    ) -> "Future[Any]":
        return self._exec_script(
            "doc.set_route_card", (route_id, title, notes)
        )

    def set_route_loading(self, route_id: str, loading: bool) -> "Future[Any]":
        """Show or hide the route header spinner while details load."""
        return self._exec_script("doc.set_route_loading", (route_id, loading))

    def add_route_card(
        self, card_id: str, title: str, notes: str,
        track: "Iterable[TrackPoint]", stats: "RouteStats | None"
    ) -> "Future[Any]":
        return self._exec_script(
            "doc.add_route_card", (card_id, title, notes, list(track), stats)
        )

    def remove_card(self, card_id: str) -> "Future[Any]":
        return self._exec_script("doc.remove_card", (card_id,))

    def move_card(self, card_id: str, after_id: str | None) -> "Future[Any]":
        return self._exec_script("doc.move_card", (card_id, after_id))
