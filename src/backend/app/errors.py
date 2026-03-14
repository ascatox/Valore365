from typing import Any


class AppError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ProviderError(ValueError):
    def __init__(
        self,
        *,
        provider: str,
        operation: str,
        symbol: str | None,
        reason: str,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.operation = operation
        self.symbol = symbol
        self.reason = reason
        self.message = message
        self.retryable = retryable
