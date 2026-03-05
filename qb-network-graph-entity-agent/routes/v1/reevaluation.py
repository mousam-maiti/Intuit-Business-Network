from __future__ import annotations

"""Re-evaluation route: POST /re-evaluate."""
from fastapi import APIRouter, Depends

from dependencies import get_reevaluation_service
from exceptions import AgentNotInitializedError
from models.resolution import ReEvaluationRequest, ReEvaluationResponse
from services.reevaluation_service import ReEvaluationService

router = APIRouter()


@router.post("/re-evaluate", response_model=ReEvaluationResponse)
async def re_evaluate(
    request: ReEvaluationRequest,
    svc: ReEvaluationService = Depends(get_reevaluation_service),
):
    """Re-evaluate a golden record after enrichment added new bucket keys."""
    if not svc:
        raise AgentNotInitializedError()
    return await svc.re_evaluate(request)
