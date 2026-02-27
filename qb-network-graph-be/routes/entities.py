"""Entity routes: GET/PATCH /entities, GET /entities/{id}."""
from fastapi import APIRouter, Request, HTTPException, Query

router = APIRouter()


@router.get("/entities")
def list_entities(
    request: Request,
    q: str = Query(None),
    industry: str = Query(None),
    company_id: str = Query(None),
):
    mysql = request.app.state.mysql
    results = mysql.get_entities(q=q, industry=industry, company_id=company_id)
    return {"data": results, "total": len(results)}


@router.get("/entities/{entity_id}")
def get_entity(request: Request, entity_id: str):
    mysql = request.app.state.mysql
    entity = mysql.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"data": entity}


@router.patch("/entities/{entity_id}")
def patch_entity(request: Request, entity_id: str, body: dict):
    mysql = request.app.state.mysql
    entity = mysql.patch_entity(entity_id, body)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"data": entity}
