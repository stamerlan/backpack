from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)


class AiError(Exception):
    def __init__(
        self, message: str, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable

    @classmethod
    def convert(cls, exc: BaseException) -> "AiError":
        if isinstance(exc, cls):
            return exc
        if isinstance(exc, BaseExceptionGroup):
            inner = [cls.convert(e) for e in exc.exceptions] or [
                cls(str(exc), False)
            ]
            retry = any(e.retryable for e in inner)
            return cls(inner[-1].message, retry)

        match exc:
            case ModelHTTPError():
                retry = exc.status_code == 429 or exc.status_code >= 500
                try:
                    details = (
                        exc.body["error"]["message"].strip()    # type: ignore
                    )
                    msg = f"{details} (status: {exc.status_code})"
                except (KeyError, AttributeError):
                    msg = f"{exc.model_name}: status {exc.status_code}"
                return cls(msg, retry)
            case ContentFilterError():
                return cls("The reply was blocked by content filters.", False)
            case IncompleteToolCall():
                return cls("The model ran out of tokens mid tool call.", True)
            case UnexpectedModelBehavior():
                return cls(exc.message, True)
            case UsageLimitExceeded():
                return cls(exc.message, False)
            case ModelAPIError():
                return cls(getattr(exc, "message", str(exc)), True)
            case AgentRunError():
                return cls(exc.message, True)
            case _:
                return cls(str(exc) or type(exc).__name__, False)
