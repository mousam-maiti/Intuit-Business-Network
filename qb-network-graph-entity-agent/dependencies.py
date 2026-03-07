from __future__ import annotations

"""FastAPI Depends() providers for the Entity Resolution Agent."""
from fastapi import Request

from services.resolution_service import ResolutionService
from services.reevaluation_service import ReEvaluationService


def get_resolution_service(request: Request) -> ResolutionService:
    return request.app.state.resolution_service


def get_reevaluation_service(request: Request) -> ReEvaluationService:
    return request.app.state.reevaluation_service
