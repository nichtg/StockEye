"""Domain-level failure shared by every service (and re-exported by ``app.api.errors``)."""


class AppError(Exception):
    """A domain-level failure with an HTTP status and a stable machine-readable code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
