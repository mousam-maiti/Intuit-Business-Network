"""
QB Network Graph Backend API — FastAPI service.

Serves 21 REST endpoints across 8 domains, querying Neo4j + MySQL.
Start: python main.py
"""
import logging
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import load_config
from exceptions import AppError, EntityNotFoundError, ClientUnavailableError
from utils import telemetry

# ── Repositories ─────────────────────────────────────────
from repositories.neo4j_entity_repo import Neo4jEntityRepository
from repositories.neo4j_relationship_repo import Neo4jRelationshipRepository
from repositories.neo4j_search_repo import Neo4jSearchRepository
from repositories.paimon_lineage_repo import PaimonLineageRepository
from repositories.paimon_resolution_repo import PaimonResolutionRepository
from repositories.mysql_native_repo import MySQLNativeRepository
from repositories.paimon_alert_repo import PaimonAlertRepository
from repositories.mysql_volume_repo import MySQLVolumeRepository

# ── Clients ──────────────────────────────────────────────
from clients.flink_sql_client import FlinkSQLClient
from clients.paimon_client import PaimonClient

# ── Services ─────────────────────────────────────────────
from services.entity_service import EntityService
from services.relationship_service import RelationshipService
from services.search_service import SearchService
from services.matching_service import MatchingService
from services.connection_service import ConnectionService
from services.native_service import NativeService
from services.alert_service import AlertService
from services.lineage_service import LineageService

# ── Routes ───────────────────────────────────────────────
from routes.v1.entities import router as entities_router
from routes.v1.relationships import router as relationships_router
from routes.v1.search import router as search_router
from routes.v1.matching import router as matching_router
from routes.v1.connections import router as connections_router
from routes.v1.native import router as native_router
from routes.v1.alerts import router as alerts_router
from routes.v1.lineage import router as lineage_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── DB driver imports (optional) ─────────────────────────
try:
    from mysql.connector import pooling
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False

try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()

    # ── Initialize OTEL telemetry ─────────────────────────
    otel_active = False
    if cfg.telemetry.enabled:
        otel_active = telemetry.setup(
            service_name=cfg.telemetry.service_name,
            otlp_endpoint=cfg.telemetry.otlp_endpoint,
            export_interval_ms=cfg.telemetry.export_interval_ms,
        )

    # ── Connect MySQL ────────────────────────────────────
    mysql_pool = None
    if HAS_MYSQL:
        mysql_pool = pooling.MySQLConnectionPool(
            pool_name="be_pool",
            pool_size=cfg.mysql.pool_size,
            host=cfg.mysql.host,
            port=cfg.mysql.port,
            user=cfg.mysql.user,
            password=cfg.mysql.password,
            database=cfg.mysql.database,
            autocommit=False,
        )
        logger.info(f"MySQL connected: {cfg.mysql.host}:{cfg.mysql.port}/{cfg.mysql.database}")
    else:
        logger.warning("mysql-connector-python not installed — MySQL unavailable")

    # ── Connect Neo4j ────────────────────────────────────
    neo4j_driver = None
    if HAS_NEO4J:
        try:
            neo4j_driver = GraphDatabase.driver(
                cfg.neo4j.uri,
                auth=(cfg.neo4j.user, cfg.neo4j.password),
                max_connection_pool_size=cfg.neo4j.max_pool_size,
            )
            neo4j_driver.verify_connectivity()
            logger.info(f"Neo4j connected: {cfg.neo4j.uri}")
        except Exception as e:
            logger.warning(f"Neo4j unavailable ({e}) — entity queries disabled")
            neo4j_driver = None
    else:
        logger.warning("neo4j driver not installed — Neo4j unavailable")

    # ── Connect Redis (search cache) ───────────────────────
    redis_client = None
    if HAS_REDIS:
        try:
            redis_client = redis.Redis(
                host=cfg.redis.host, port=cfg.redis.port,
                db=cfg.redis.db, decode_responses=True,
                socket_connect_timeout=3,
            )
            redis_client.ping()
            logger.info(f"Redis connected: {cfg.redis.host}:{cfg.redis.port}/db{cfg.redis.db}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — search cache disabled")
            redis_client = None
    else:
        logger.warning("redis package not installed — search cache disabled")

    # ── Connect Flink SQL Gateway (for writes only) ──────
    flink_client = FlinkSQLClient(base_url=cfg.flink_sql.url, timeout=cfg.flink_sql.timeout)
    flink_client.connect()

    # ── Connect Paimon direct reader (for reads) ─────────
    paimon_client = PaimonClient(warehouse_path=cfg.paimon.warehouse_path)
    paimon_client.connect()

    # ── Build repositories ───────────────────────────────
    entity_repo = Neo4jEntityRepository(neo4j_driver, cfg.neo4j.database)
    relationship_repo = Neo4jRelationshipRepository(neo4j_driver, cfg.neo4j.database, entity_repo)
    search_repo = Neo4jSearchRepository(neo4j_driver, cfg.neo4j.database)

    # Paimon-backed repos (pypaimon for reads, Flink SQL Gateway for writes)
    lineage_repo = PaimonLineageRepository(paimon_client, sync_base_url=cfg.sync.url, flink_client=flink_client)
    resolution_repo = PaimonResolutionRepository(paimon_client, flink_client=flink_client, sync_base_url=cfg.sync.url)
    alert_repo = PaimonAlertRepository(paimon_client, flink_client=flink_client)

    # MySQL-backed repos (OLTP source data only)
    native_repo = MySQLNativeRepository(mysql_pool) if mysql_pool else None
    volume_repo = MySQLVolumeRepository(mysql_pool, flink_client) if mysql_pool else None

    # ── Build services ───────────────────────────────────
    app.state.entity_service = EntityService(entity_repo, fallback_repo=volume_repo)
    app.state.relationship_service = RelationshipService(relationship_repo, volume_repo)
    app.state.search_service = SearchService(
        search_repo, redis_client=redis_client,
        search_ttl=cfg.redis.search_ttl,
        search_max_keys=cfg.redis.search_max_keys,
    )
    app.state.matching_service = MatchingService(resolution_repo, entity_repo=entity_repo, relationship_repo=relationship_repo, sync_url=cfg.sync.url)
    app.state.connection_service = ConnectionService(
        paimon_client, alert_repo,
        neo4j_driver=neo4j_driver, neo4j_database=cfg.neo4j.database,
        entity_repo=entity_repo, relationship_repo=relationship_repo,
    )
    app.state.native_service = NativeService(native_repo)
    app.state.alert_service = AlertService(alert_repo)
    app.state.lineage_service = LineageService(lineage_repo, entity_repo=entity_repo)

    # ── HTTP client for entity agent ─────────────────────
    app.state.http_client = httpx.AsyncClient(
        base_url=cfg.entity_agent.url,
        timeout=cfg.entity_agent.timeout,
    )
    app.state.cfg = cfg

    logger.info(
        f"QB Network Graph BE started  "
        f"MySQL={cfg.mysql.host}:{cfg.mysql.port}/{cfg.mysql.database}  "
        f"Neo4j={cfg.neo4j.uri}  "
        f"EntityAgent={cfg.entity_agent.url}  "
        f"OTEL={'ACTIVE' if otel_active else 'disabled'}  "
        f"port={cfg.server.port}"
    )

    yield

    # ── Shutdown ─────────────────────────────────────────
    await app.state.http_client.aclose()
    paimon_client.close()
    flink_client.close()
    if neo4j_driver:
        neo4j_driver.close()
        logger.info("Neo4j driver closed")
    logger.info("All connections released")


app = FastAPI(title="QB Network Graph API", lifespan=lifespan)

# ── OTEL auto-instrumentation (must be at module level, before first request) ──
telemetry.instrument_app(app)


# ── Exception handlers ───────────────────────────────────

@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(status_code=404, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(ClientUnavailableError)
async def client_unavailable_handler(request: Request, exc: ClientUnavailableError):
    return JSONResponse(status_code=503, content={"error": exc.code, "detail": exc.message})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=500, content={"error": exc.code, "detail": exc.message})


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
