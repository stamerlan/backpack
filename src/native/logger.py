import logging
from typing import Protocol


class NativeLogger(Protocol):
    @property
    def level(self) -> int: ...

    def write(self, level: int, name: str, func: str, msg: str) -> None: ...


class NativeLoggerHandler(logging.Handler):
    def __init__(self, logger: NativeLogger) -> None:
        super().__init__()
        self.logger = logger
        # native logger adds time, thread, level and source. The formatter
        # appends exception and stack text.
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.logger.write(
                record.levelno, record.name, record.funcName,
                self.format(record)
            )
        except Exception:
            self.handleError(record)


def setup(logger: NativeLogger) -> None:
    root = logging.getLogger()
    root.handlers[:] = [NativeLoggerHandler(logger)]
    root.setLevel(logger.level)
    logging.captureWarnings(True)
