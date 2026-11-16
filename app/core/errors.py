class AuthError(Exception):
    """An expected authentication failure, without secret values in its message."""

    def __init__(self, code: str, message: str, status_code: int = 401,
                 retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after
