"""Adapter-layer exceptions."""


class AdapterException(Exception):
    """Base class for adapter-layer exceptions."""


class LimitExceededException(AdapterException):
    """Raised when a rate or quota limit is exceeded at the adapter boundary."""

    def __init__(
        self,
        message: str = "Limit exceeded in adapter layer",
        start: str = "",
        end: str = "",
        retry_after_secs: int = 3600,
    ):
        super().__init__(message)
        self.start = start
        self.end = end
        self.retry_after_secs = retry_after_secs
