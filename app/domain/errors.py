class DomainError(Exception):
    """Base class for expected business errors."""
    
class TicketNotFoundError(DomainError):
    """Raised when a ticket is not existing."""

class InvalidStatusTransitionError(DomainError):
    """Raised when a status change violates the workflow."""
