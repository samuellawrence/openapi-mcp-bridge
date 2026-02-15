"""Safety guardrails for API operations."""

from pydantic import BaseModel


class GuardrailResult(BaseModel):
    """Result of a guardrail check."""

    allowed: bool
    warning: str | None = None


class Guardrails:
    """
    Safety guardrails for API operations.

    Identifies and controls destructive operations (DELETE, PUT, PATCH)
    requiring explicit confirmation before execution.
    """

    DEFAULT_DESTRUCTIVE_METHODS = ["DELETE", "PUT", "PATCH"]

    def __init__(self, destructive_methods: list[str] | None = None):
        """
        Initialize guardrails.

        Args:
            destructive_methods: List of HTTP methods considered destructive.
                Defaults to DELETE, PUT, PATCH.
        """
        if destructive_methods is None:
            destructive_methods = self.DEFAULT_DESTRUCTIVE_METHODS
        self.destructive_methods = [m.upper() for m in destructive_methods]

    def is_destructive(self, method: str) -> bool:
        """
        Check if an HTTP method is considered destructive.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)

        Returns:
            True if the method is destructive.
        """
        return method.upper() in self.destructive_methods

    def check_operation(
        self,
        method: str,
        path: str,
        confirmed: bool = False,
    ) -> GuardrailResult:
        """
        Check if an operation is allowed to proceed.

        Args:
            method: HTTP method.
            path: API path being called.
            confirmed: Whether the user has confirmed the destructive operation.

        Returns:
            GuardrailResult indicating if the operation is allowed.
        """
        method = method.upper()

        if not self.is_destructive(method):
            # Safe methods always allowed
            return GuardrailResult(allowed=True)

        if confirmed:
            # Destructive but confirmed
            return GuardrailResult(allowed=True)

        # Destructive and not confirmed - return warning
        warning = (
            f"This is a destructive operation ({method} {path}). "
            f"Set confirmed=true to proceed with this operation."
        )
        return GuardrailResult(allowed=False, warning=warning)
