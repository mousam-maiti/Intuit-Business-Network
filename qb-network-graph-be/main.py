"""
QB Network Graph Backend API — FastAPI service.

Serves 21 REST endpoints across 6 domains, querying MySQL directly.
Start: python main.py
"""
import logging
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from config import load_config
from clients.mysql_client import MySQLClient

# ── Routes ───────────────────────────────────────────────

from routes.entities import router as entities_router
from routes.relationships import router as relationships_router
from routes.search import router as search_router
from routes.matching import router as matching_router
from routes.connections import router as connections_router
from routes.native import router as native_router
from routes.alerts import router as alerts_router
from routes.lineage import router as lineage_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    mysql = MySQLClient(cfg.mysql)
    await mysql.connect()
    app.state.mysql = mysql
    app.state.cfg = cfg
    app.state.http_client = httpx.AsyncClient(
        base_url=cfg.entity_agent.url,
        timeout=cfg.entity_agent.timeout,
    )
    logger.info(
        f"QB Network Graph BE started  "
        f"MySQL={cfg.mysql.host}:{cfg.mysql.port}/{cfg.mysql.database}  "
        f"EntityAgent={cfg.entity_agent.url}  "
        f"port={cfg.server.port}"
    )
    yield
    await app.state.http_client.aclose()
    await mysql.close()


app = FastAPI(title="QB Network Graph API", lifespan=lifespan)

# ── CORS ─────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routes under /api/v1 ───────────────────────────

api = APIRouter(prefix="/api/v1")
api.include_router(entities_router)
api.include_router(relationships_router)
api.include_router(search_router)
api.include_router(matching_router)
api.include_router(connections_router)
api.include_router(native_router)
api.include_router(alerts_router)
api.include_router(lineage_router)

app.include_router(api)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run(
        "main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=True,
    )
