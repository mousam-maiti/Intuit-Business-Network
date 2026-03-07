"""Custom exception hierarchy for the BE service."""


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class EntityNotFoundError(AppError):
    def __init__(self, entity_id: str):
        super().__init__(f"Entity not found: {entity_id}", "ENTITY_NOT_FOUND")
        self.entity_id = entity_id


class ResolutionConflictError(AppError):
    def __init__(self, match_id: str, detail: str = ""):
        super().__init__(
            f"Resolution conflict for match {match_id}: {detail}",
            "RESOLUTION_CONFLICT",
        )
        self.match_id = match_id


class ClientUnavailableError(AppError):
    def __init__(self, client_name: str):
        super().__init__(f"{client_name} is unavailable", "CLIENT_UNAVAILABLE")
        self.client_name = client_name


class ValidationError(AppError):
    def __init__(self, detail: str):
        super().__init__(detail, "VALIDATION_ERROR")
