from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    IncompleteToolCall,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)

from ..i18n import i18n
from ..model import ChatCardAction


class AiError(Exception):
    def __init__(
        self,
        message: str,
        actions: ChatCardAction | tuple[ChatCardAction, ...] = ()
    ) -> None:
        super().__init__(message)
        self.message = message
        self.actions: tuple[ChatCardAction, ...] = (
            actions if isinstance(actions, tuple) else (actions,)
        )

    @classmethod
    def convert(cls, exc: BaseException) -> "AiError":
        if isinstance(exc, cls):
            return exc
        if isinstance(exc, BaseExceptionGroup):
            inner = [cls.convert(e) for e in exc.exceptions] or [cls(str(exc))]
            return cls(inner[-1].message, inner[-1].actions)

        retry_action = ChatCardAction(
            id="retry", label=i18n.gettext("Retry"), appearance="primary"
        )

        match exc:
            case ModelHTTPError():
                can_retry = exc.status_code == 429 or exc.status_code >= 500
                try:
                    details = (
                        exc.body["error"]["message"].strip()    # type: ignore
                    )
                    msg = i18n.gettext(
                        "{details} (status: {status})",
                        details=details, status=exc.status_code
                    )
                except (KeyError, AttributeError):
                    msg = i18n.gettext(
                        "{model}: status {status}",
                        model=exc.model_name, status=exc.status_code
                    )
                return cls(msg, retry_action if can_retry else ())
            case ContentFilterError():
                return cls(i18n.gettext(
                    "The reply was blocked by content filters."
                ))
            case IncompleteToolCall():
                return cls(i18n.gettext(
                    "The model ran out of tokens mid tool call."
                ), retry_action)
            case UnexpectedModelBehavior():
                return cls(exc.message, retry_action)
            case UsageLimitExceeded():
                return cls(exc.message)
            case ModelAPIError():
                return cls(getattr(exc, "message", str(exc)), retry_action)
            case AgentRunError():
                return cls(exc.message, retry_action)
            case _:
                return cls(str(exc) or type(exc).__name__)
