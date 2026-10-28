"""Domain error shared by the store and the template renderer."""


class InvalidInput(ValueError):
    """Client-supplied data failed domain validation (HTTP 422). Any other ValueError is a bug."""
