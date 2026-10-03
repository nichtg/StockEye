"""Provider error taxonomy. Callers branch on the type, never on message text."""


class ProviderError(Exception):
    """Base class. ``provider`` names the adapter that failed."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider


class TransientProviderError(ProviderError):
    """Timeouts, connection resets and 5xx responses. Safe to retry."""


class RateLimitedError(TransientProviderError):
    """The vendor answered 429. ``retry_after`` is in seconds when the vendor said so."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(provider, "rate limited by vendor")
        self.retry_after = retry_after


class QuotaExhaustedError(ProviderError):
    """Our own quota ledger blocked the call before it was made."""


class CircuitOpenError(ProviderError):
    """The circuit breaker is open after repeated failures; the call was not attempted."""


class ProviderDataError(ProviderError):
    """The vendor answered, but the payload was malformed or empty. Not retried."""


class SymbolNotFoundError(ProviderError):
    """The vendor does not know this symbol."""
