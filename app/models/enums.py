from enum import StrEnum

class Role(StrEnum):
    REQUESTER = "requester"
    TECHNICIAN = "technician"
    SUPERVISOR = "supervisor"
    ADMINISTRATOR = "administrator"

class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    
CATEGORIES = ["General", "Hardware", "Software", "Network", "Security", "Other"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
