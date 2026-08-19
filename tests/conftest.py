from collections.abc import Iterator

import pytest

from core.js_worker import JsWorker
from tests.fake_window import FakeWindow


@pytest.fixture
def js() -> Iterator[JsWorker]:
    q = JsWorker()
    try:
        yield q
    finally:
        q.shutdown()


@pytest.fixture
def win() -> FakeWindow:
    return FakeWindow()
