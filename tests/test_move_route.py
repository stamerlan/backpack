from core.model import Document, MoveRoute, RouteData
from core.model.store import Store


def make_store(*route_ids: str) -> Store:
    store = Store()
    for rid in route_ids:
        store.put_route(RouteData(id=rid))
    return store


def order(store: Store) -> list[str]:
    return [r.id for r in store.routes()]


def test_move_to_front_when_after_id_is_none() -> None:
    store = make_store("a", "b", "c")
    store.move_route("c", None)
    assert order(store) == ["c", "a", "b"]


def test_move_after_a_middle_route() -> None:
    store = make_store("a", "b", "c")
    store.move_route("a", "b")
    assert order(store) == ["b", "a", "c"]


def test_move_after_the_last_route() -> None:
    store = make_store("a", "b", "c")
    store.move_route("a", "c")
    assert order(store) == ["b", "c", "a"]


def test_move_after_self_is_a_noop() -> None:
    store = make_store("a", "b", "c")
    store.move_route("b", "b")
    assert order(store) == ["a", "b", "c"]


def test_move_unknown_route_is_ignored() -> None:
    store = make_store("a", "b")
    store.move_route("z", None)
    assert order(store) == ["a", "b"]


def test_move_after_unknown_target_is_ignored() -> None:
    store = make_store("a", "b")
    store.move_route("a", "z")
    assert order(store) == ["a", "b"]


def test_move_keeps_the_front_route_when_after_id_is_none() -> None:
    store = make_store("a", "b", "c")
    store.move_route("a", None)
    assert order(store) == ["a", "b", "c"]


def test_move_route_change_applies_through_a_document() -> None:
    doc = Document.from_dict(
        {"routes": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    )
    with doc.edit(object()) as ed:
        ed.apply(MoveRoute("c", None))
    assert doc.route_ids() == ("c", "a", "b")


def test_move_route_change_after_target_through_a_document() -> None:
    doc = Document.from_dict(
        {"routes": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    )
    with doc.edit(object()) as ed:
        ed.apply(MoveRoute("a", "b"))
    assert doc.route_ids() == ("b", "a", "c")
