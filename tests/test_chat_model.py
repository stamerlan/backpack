"""Tests for the chat content-stream model.

Covers round-trip serialization for each ChatItem kind, the item-grouping
logic used by ask_assist, and on_change -> ui.assist.* dispatch.
"""
from typing import Any, cast
from unittest.mock import MagicMock, call

import webview

from backpack import model
from backpack.js_worker import JsWorker
from backpack.model import (
    AddChat,
    AppendChatTurn,
    ChatCard,
    ChatCardAction,
    ChatData,
    ChatReply,
    ChatThinking,
    ChatTurn,
    Document,
    RemoveChat,
    RemoveChatTurn,
    SetChatTitle,
)
from backpack.ui import Assist, UI
from tests.fake_window import FakeWindow


# -- Model round-trip tests --


def test_roundtrip_thinking_item() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "Test",
            "turns": [{
                "id": "t1",
                "prompt": "hi",
                "items": [{"kind": "thinking", "text": "hmm"}],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    assert len(chat.turns) == 1
    assert chat.turns[0].items == (ChatThinking(text="hmm"),)

    d = doc.to_dict()
    items = d["chats"][0]["turns"][0]["items"]
    assert items == [{"kind": "thinking", "text": "hmm"}]


def test_roundtrip_reply_item() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "Test",
            "turns": [{
                "id": "t1",
                "prompt": "hi",
                "items": [{"kind": "reply", "text": "hello!"}],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    assert chat.turns[0].items == (ChatReply(text="hello!"),)

    d = doc.to_dict()
    items = d["chats"][0]["turns"][0]["items"]
    assert items == [{"kind": "reply", "text": "hello!"}]


def test_roundtrip_card_item_with_actions() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "Test",
            "turns": [{
                "id": "t1",
                "prompt": "hi",
                "items": [{
                    "kind": "card",
                    "card_kind": "error",
                    "title": "Oops",
                    "text": "Something failed",
                    "actions": [
                        {"id": "retry", "label": "Retry",
                         "appearance": "primary"},
                        {"id": "dismiss", "label": "Dismiss",
                         "appearance": "secondary"},
                    ],
                }],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    card = chat.turns[0].items[0]
    assert isinstance(card, ChatCard)
    assert card.card_kind == "error"
    assert card.title == "Oops"
    assert card.text == "Something failed"
    assert card.actions == (
        ChatCardAction(id="retry", label="Retry", appearance="primary"),
        ChatCardAction(id="dismiss", label="Dismiss",
                       appearance="secondary"),
    )

    d = doc.to_dict()
    raw = d["chats"][0]["turns"][0]["items"][0]
    assert raw["kind"] == "card"
    assert raw["card_kind"] == "error"
    assert raw["title"] == "Oops"
    assert len(raw["actions"]) == 2
    assert raw["actions"][0]["id"] == "retry"


def test_roundtrip_card_without_actions() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "T",
            "turns": [{
                "id": "t1",
                "prompt": "p",
                "items": [{
                    "kind": "card",
                    "card_kind": "message",
                    "title": "Info",
                    "text": "Done",
                }],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    card = chat.turns[0].items[0]
    assert isinstance(card, ChatCard)
    assert card.card_kind == "message"
    assert card.actions == ()


def test_roundtrip_multiple_items_in_turn() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "Chat",
            "turns": [{
                "id": "t1",
                "prompt": "what?",
                "items": [
                    {"kind": "thinking", "text": "let me think"},
                    {"kind": "reply", "text": "answer"},
                    {"kind": "card", "card_kind": "suggest",
                     "title": "", "text": "try this"},
                ],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    items = chat.turns[0].items
    assert len(items) == 3
    assert isinstance(items[0], ChatThinking)
    assert isinstance(items[1], ChatReply)
    assert isinstance(items[2], ChatCard)

    rt = Document.from_dict(doc.to_dict())
    rt_chat = rt.chat("c1")
    assert rt_chat is not None
    assert rt_chat.turns[0].items == items


def test_roundtrip_empty_chat() -> None:
    doc = Document.from_dict({
        "chats": [{"id": "c1", "title": "Empty"}],
    })
    chat = doc.chat("c1")
    assert chat is not None
    assert chat.turns == ()
    assert chat.title == "Empty"

    d = doc.to_dict()
    assert d["chats"][0]["turns"] == []


def test_roundtrip_preserves_turn_id_and_prompt() -> None:
    doc = Document.from_dict({
        "chats": [{
            "id": "c1",
            "title": "C",
            "turns": [{
                "id": "custom-turn-id",
                "prompt": "my question",
                "items": [],
            }],
        }],
    })
    chat = doc.chat("c1")
    assert chat is not None
    assert chat.turns[0].id == "custom-turn-id"
    assert chat.turns[0].prompt == "my question"


# -- Item grouping tests --


def test_item_grouping_coalesces_reply_tokens() -> None:
    """Simulates the grouping logic in ask_assist: consecutive reply tokens
    get coalesced into a single ChatReply item."""
    items = list[model.ChatItem]()
    tokens = ["He", "llo", " wor", "ld"]

    for text in tokens:
        if items and isinstance(items[-1], ChatReply):
            items[-1] = ChatReply(items[-1].text + text)
        else:
            items.append(ChatReply(text))

    assert len(items) == 1
    assert items[0] == ChatReply(text="Hello world")


def test_item_grouping_coalesces_thinking_tokens() -> None:
    items = list[model.ChatItem]()
    tokens = ["Hmm", ", let", " me"]

    for text in tokens:
        if items and isinstance(items[-1], ChatThinking):
            items[-1] = ChatThinking(items[-1].text + text)
        else:
            items.append(ChatThinking(text))

    assert len(items) == 1
    assert items[0] == ChatThinking(text="Hmm, let me")


def test_item_grouping_thinking_then_reply() -> None:
    """A switch from thinking to reply starts a new block."""
    items = list[model.ChatItem]()

    def on_think(text: str) -> None:
        if items and isinstance(items[-1], ChatThinking):
            items[-1] = ChatThinking(items[-1].text + text)
        else:
            items.append(ChatThinking(text))

    def on_text(text: str) -> None:
        if items and isinstance(items[-1], ChatReply):
            items[-1] = ChatReply(items[-1].text + text)
        else:
            items.append(ChatReply(text))

    on_think("step1")
    on_think(" step2")
    on_text("ans")
    on_text("wer")

    assert len(items) == 2
    assert items[0] == ChatThinking(text="step1 step2")
    assert items[1] == ChatReply(text="answer")


def test_item_grouping_card_breaks_reply_block() -> None:
    """A card inserted after a reply starts a new block when reply resumes."""
    items = list[model.ChatItem]()

    def on_text(text: str) -> None:
        if items and isinstance(items[-1], ChatReply):
            items[-1] = ChatReply(items[-1].text + text)
        else:
            items.append(ChatReply(text))

    on_text("part1")
    on_text(" part2")
    items.append(ChatCard(card_kind="message", text="tool result"))
    on_text("part3")

    assert len(items) == 3
    assert items[0] == ChatReply(text="part1 part2")
    assert isinstance(items[1], ChatCard)
    assert items[2] == ChatReply(text="part3")


def test_item_grouping_interleaved_thinking_and_reply() -> None:
    """Multiple thinking/reply blocks across tool calls."""
    items = list[model.ChatItem]()

    def on_think(text: str) -> None:
        if items and isinstance(items[-1], ChatThinking):
            items[-1] = ChatThinking(items[-1].text + text)
        else:
            items.append(ChatThinking(text))

    def on_text(text: str) -> None:
        if items and isinstance(items[-1], ChatReply):
            items[-1] = ChatReply(items[-1].text + text)
        else:
            items.append(ChatReply(text))

    on_think("t1")
    on_text("r1")
    on_think("t2")
    on_text("r2")

    assert len(items) == 4
    assert items[0] == ChatThinking(text="t1")
    assert items[1] == ChatReply(text="r1")
    assert items[2] == ChatThinking(text="t2")
    assert items[3] == ChatReply(text="r2")


# -- on_change -> ui.assist dispatch tests --


class FakeJsWorker:
    """Records calls instead of dispatching to a real window."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def submit(self, func: str, args: tuple[Any, ...]) -> Any:
        self.calls.append((func, args))
        fut: Any = MagicMock()
        return fut


def make_app_on_change(
    origin: object | None = None,
) -> tuple[Document, "FakeJsWorker", Any]:
    """Set up a Document + UI wired like App.on_change.

    Returns (doc, fake_js, on_change_fn). The on_change_fn uses origin
    as the api object (the identity check for echo suppression).
    """
    doc = Document()
    fake_js = FakeJsWorker()
    ui = UI(cast(JsWorker, fake_js))
    api_origin = origin if origin is not None else object()

    def on_change(change: model.Change, chg_origin: model.Origin) -> None:
        if isinstance(change, AddChat):
            ui.assist.new_chat(change.chat.id, change.chat.title)
        elif isinstance(change, RemoveChat):
            ui.assist.del_chat(change.chat_id)
        elif isinstance(change, SetChatTitle):
            ui.assist.set_chat_title(change.chat_id, change.title)
        elif isinstance(change, AppendChatTurn):
            pass
        elif isinstance(change, RemoveChatTurn):
            ui.assist.del_turn(change.chat_id, change.turn_id)

    doc.subscribe(on_change)
    return doc, fake_js, api_origin


def test_on_change_add_chat_dispatches_new_chat() -> None:
    doc, fake_js, origin = make_app_on_change()
    chat = ChatData(id="chat-abc", title="My Chat")
    with doc.edit(origin) as ed:
        ed.apply(AddChat(chat))

    assert ("assist.new_chat", ("chat-abc", "My Chat")) in fake_js.calls


def test_on_change_remove_chat_dispatches_del_chat() -> None:
    doc, fake_js, origin = make_app_on_change()
    chat = ChatData(id="chat-xyz")
    with doc.edit(origin) as ed:
        ed.apply(AddChat(chat))

    fake_js.calls.clear()
    with doc.edit(origin) as ed:
        ed.apply(RemoveChat("chat-xyz"))

    assert ("assist.del_chat", ("chat-xyz",)) in fake_js.calls


def test_on_change_set_chat_title_dispatches() -> None:
    doc, fake_js, origin = make_app_on_change()
    chat = ChatData(id="chat-t")
    with doc.edit(origin) as ed:
        ed.apply(AddChat(chat))

    fake_js.calls.clear()
    with doc.edit(origin) as ed:
        ed.apply(SetChatTitle("chat-t", "Renamed"))

    assert ("assist.set_chat_title", ("chat-t", "Renamed")) in fake_js.calls


def test_on_change_append_turn_is_noop() -> None:
    doc, fake_js, origin = make_app_on_change()
    chat = ChatData(id="chat-n")
    with doc.edit(origin) as ed:
        ed.apply(AddChat(chat))

    fake_js.calls.clear()
    turn = ChatTurn(id="turn-1", prompt="hi", items=(ChatReply(text="yo"),))
    with doc.edit(origin) as ed:
        ed.apply(AppendChatTurn("chat-n", turn))

    assert not any(
        c[0] == "assist.new_turn" for c in fake_js.calls
    )


def test_on_change_remove_turn_dispatches_del_turn() -> None:
    doc, fake_js, origin = make_app_on_change()
    chat = ChatData(id="chat-r")
    with doc.edit(origin) as ed:
        ed.apply(AddChat(chat))

    turn = ChatTurn(id="turn-del", prompt="x")
    with doc.edit(origin) as ed:
        ed.apply(AppendChatTurn("chat-r", turn))

    fake_js.calls.clear()
    with doc.edit(origin) as ed:
        ed.apply(RemoveChatTurn("chat-r", "turn-del"))

    assert ("assist.del_turn", ("chat-r", "turn-del")) in fake_js.calls
