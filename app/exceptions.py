"""Application-specific exceptions."""


class RefundOperatorError(Exception):
    """Base exception for expected refund operator failures."""


class ConfigurationError(RefundOperatorError):
    """Raised when application configuration is invalid or incomplete."""


class DatabaseError(RefundOperatorError):
    """Raised when a database operation cannot be completed safely."""


class RecordNotFoundError(RefundOperatorError):
    """Raised when a required persisted record does not exist."""


class InvalidAgentStateError(RefundOperatorError):
    """Raised when a persisted workflow state is unknown or inconsistent."""


class InvalidStateTransitionError(RefundOperatorError):
    """Raised when code attempts a disallowed workflow transition."""


class PaymentGatewayError(RefundOperatorError):
    """Base exception for mock payment gateway failures."""


class PaymentGatewayTimeoutError(PaymentGatewayError):
    """Raised when the gateway response is lost after an ambiguous request."""


class GatewayUnavailableError(PaymentGatewayError):
    """Raised when refund status cannot be retrieved from the gateway."""


class LLMProviderError(RefundOperatorError):
    """Raised when an LLM provider call or response fails."""


class UnsupportedLLMProviderError(ConfigurationError):
    """Raised when the configured LLM provider is not supported."""
