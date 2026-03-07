from __future__ import annotations

"""Resolution route: POST /resolve."""
from fastapi import APIRouter, Depends

from dependencies import get_resolution_service
from exceptions import AgentNotInitializedError
from models.resolution import ResolutionRequest, ResolutionResponse
from services.resolution_service import ResolutionService

router = APIRouter()


@router.post("/resolve", response_model=ResolutionResponse)
async def resolve(
    request: ResolutionRequest,
    svc: ResolutionService = Depends(get_resolution_service),
):
    """Resolve an orphan record: find matching golden record or create new."""
    if not svc:
        raise AgentNotInitializedError()
    return await svc.resolve(request)
