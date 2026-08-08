class AlreadyClockedInError(Exception):
    """Raised when clock_in() is called for a user who already has an active shift."""
    pass


class NotClockedInError(Exception):
    """Raised when clock_out() is called for a user with no active shift."""
    pass
