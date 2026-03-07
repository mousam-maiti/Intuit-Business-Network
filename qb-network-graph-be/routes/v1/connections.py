"""Connection routes: GET /connections/auto, GET /connections/manual, POST /connections, POST /connections/add-network, POST /connections/remove."""
from fastapi import APIRouter, Depends

from dependencies import get_connection_service
from models.api import AddConnectionRequest, AddExistingConnectionRequest, RemoveConnectionRequest
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
    body: AddConnectionRequest,
    svc: ConnectionService = Depends(get_connection_service),
):
    payload = body.model_dump()
    result = svc.add(payload)
    return {"data": result}


@router.post("/connections/add-network")
async def add_existing_connection(
    body: AddExistingConnectionRequest,
    svc: ConnectionService = Depends(get_connection_service),
):
    result = svc.add_existing(
        golden_record_id=body.goldenRecordId,
        conn_type=body.connType,
    )
    return {"data": result}


@router.post("/connections/remove")
async def remove_connection(
    body: RemoveConnectionRequest,
    svc: ConnectionService = Depends(get_connection_service),
):
    result = svc.remove_connection(entity_id=body.entityId)
    return {"data": result}
