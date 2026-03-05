"""Native perspective routes: overrides + merges."""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_native_service
from exceptions import EntityNotFoundError
from models.api import CreateMergeRequest
from services.native_service import NativeService

router = APIRouter()


# ── Overrides ────────────────────────────────────────────

@router.get("/native/overrides")
def get_all_overrides(svc: NativeService = Depends(get_native_service)):
    return svc.get_all_overrides()


@router.get("/native/overrides/{entity_id}")
def get_override(entity_id: str, svc: NativeService = Depends(get_native_service)):
    return svc.get_override(entity_id)


@router.patch("/native/overrides/{entity_id}")
def save_override(entity_id: str, body: dict, svc: NativeService = Depends(get_native_service)):
    return svc.save_override(entity_id, body)


@router.delete("/native/overrides/{entity_id}/{field}")
def delete_override_field(entity_id: str, field: str, svc: NativeService = Depends(get_native_service)):
    return svc.delete_override_field(entity_id, field)


# ── Merges ───────────────────────────────────────────────

@router.get("/native/merges")
def get_merges(svc: NativeService = Depends(get_native_service)):
    return svc.get_merges()


@router.post("/native/merges")
def create_merge(body: CreateMergeRequest, svc: NativeService = Depends(get_native_service)):
    return svc.create_merge(body.model_dump())


@router.delete("/native/merges/{merge_id}")
def delete_merge(merge_id: str, svc: NativeService = Depends(get_native_service)):
    try:
        return svc.delete_merge(merge_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Merge not found")
