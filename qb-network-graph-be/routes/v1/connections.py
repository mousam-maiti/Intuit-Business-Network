"""Connection routes: GET /connections/auto, GET /connections/manual, POST /connections."""
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from dependencies import get_connection_service
from models.api import AddConnectionRequest
from services.connection_service import ConnectionService

router = APIRouter()


@router.get("/connections/auto")
def get_auto_connections(svc: ConnectionService = Depends(get_connection_service)):
    return {"data": svc.get_auto()["data"]}


@router.get("/connections/manual")
def get_manual_connections(svc: ConnectionService = Depends(get_connection_service)):
    return {"data": svc.get_manual()["data"]}


@router.post("/connections")
async def add_connection(
    request: Request,
    body: AddConnectionRequest,
    background_tasks: BackgroundTasks,
    svc: ConnectionService = Depends(get_connection_service),
):
    payload = body.model_dump()
    result = svc.add(payload)

    background_tasks.add_task(
        svc.resolve_async, request.app, result["id"], payload,
    )

    return {"data": result}
