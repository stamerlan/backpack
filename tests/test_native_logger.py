"""Tests for native.logger - Python logging routed to a native sink."""
import logging
import sys
import warnings
from collections.abc import Iterator

import pytest

from native.logger import NativeLoggerHandler, setup


class FakeSink:
    def __init__(self, level: int = logging.INFO) -> None:
        self.level = level
        self.records: list[tuple[int, str, str, str]] = []

    def write(self, level: int, name: str, func: str, msg: str) -> None:
        self.records.append((level, name, func, msg))


@pytest.fixture
def root() -> Iterator[logging.Logger]:
    """Restore the root logger and warnings capture after a test"""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.captureWarnings(False)


class TestSinkHandler:
    def test_maps_record_fields(self) -> None:
        sink = FakeSink()
        log = logging.getLogger("test.sink.fields")
        log.propagate = False
        log.addHandler(NativeLoggerHandler(sink))
        try:
            log.warning("value %d", 42)
        finally:
            log.handlers.clear()
            log.propagate = True
        assert sink.records == [(
            logging.WARNING, "test.sink.fields", "test_maps_record_fields",
            "value 42"
        )]

    def test_appends_exception_text(self) -> None:
        sink = FakeSink()
        record = logging.LogRecord(
            "x", logging.ERROR, __file__, 1, "failed", None, None
        )
        try:
            raise ValueError("boom")
        except ValueError:
            record.exc_info = sys.exc_info()
        NativeLoggerHandler(sink).handle(record)
        msg = sink.records[0][3]
        assert msg.startswith("failed\nTraceback")
        assert msg.endswith("ValueError: boom")

    def test_sink_error_goes_to_handle_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class BrokenSink(FakeSink):
            def write(self, level: int, name: str, func: str,
                      msg: str) -> None:
                raise OSError("disk full")

        handler = NativeLoggerHandler(BrokenSink())
        errors: list[logging.LogRecord] = []
        monkeypatch.setattr(handler, "handleError", errors.append)
        record = logging.LogRecord(
            "x", logging.INFO, __file__, 1, "msg", None, None
        )
        handler.handle(record)
        assert errors == [record]


class TestInstall:
    def test_replaces_root_handlers(self, root: logging.Logger) -> None:
        root.addHandler(logging.NullHandler())
        setup(FakeSink(logging.DEBUG))
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], NativeLoggerHandler)
        assert root.level == logging.DEBUG

    def test_level_filters_records(self, root: logging.Logger) -> None:
        sink = FakeSink(logging.INFO)
        setup(sink)
        logging.getLogger("test.install").debug("hidden")
        logging.getLogger("test.install").info("shown")
        assert [r[3] for r in sink.records] == ["shown"]

    def test_captures_warnings(self, root: logging.Logger) -> None:
        sink = FakeSink()
        setup(sink)
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.warn("careful", UserWarning)
        assert len(sink.records) == 1
        level, name, _, msg = sink.records[0]
        assert (level, name) == (logging.WARNING, "py.warnings")
        assert "UserWarning: careful" in msg
