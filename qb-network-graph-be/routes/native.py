"""Native perspective routes: overrides + merges."""
from fastapi import APIRouter, Request, HTTPException

from models.api import CreateMergeRequest

router = APIRouter()


# ── Overrides ────────────────────────────────────────────

@router.get("/native/overrides")
def get_all_overrides(request: Request):
    mysql = request.app.state.mysql
    overrides = mysql.get_all_overrides()
    return {"data": overrides}


@router.get("/native/overrides/{entity_id}")
def get_override(request: Request, entity_id: str):
    mysql = request.app.state.mysql
    override = mysql.get_override(entity_id)
    return {"data": override}


@router.patch("/native/overrides/{entity_id}")
def save_override(request: Request, entity_id: str, body: dict):
    mysql = request.app.state.mysql
    result = mysql.save_override(entity_id, body)
    return {"data": result}


@router.delete("/native/overrides/{entity_id}/{field}")
def delete_override_field(request: Request, entity_id: str, field: str):
    mysql = request.app.state.mysql
    result = mysql.delete_override_field(entity_id, field)
    return {"data": result}


# ── Merges ───────────────────────────────────────────────

@router.get("/native/merges")
def get_merges(request: Request):
    mysql = request.app.state.mysql
    merges = mysql.get_merges()
    return {"data": merges}


@router.post("/native/merges")
def create_merge(request: Request, body: CreateMergeRequest):
    mysql = request.app.state.mysql
    result = mysql.create_merge(body.model_dump())
    return {"data": result}


@router.delete("/native/merges/{merge_id}")
def delete_merge(request: Request, merge_id: str):
    mysql = request.app.state.mysql
    result = mysql.delete_merge(merge_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Merge not found")
    return {"data": result}
