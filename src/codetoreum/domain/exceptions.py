"""Domain layer exceptions."""


class DomainError(Exception):
    """Base exception for domain layer errors."""

    def __init__(self, message: str):
        """
        Initialize domain error.

        Args:
            message: Error message describing the business rule violation
        """
        self.message = message
        super().__init__(self.message)
