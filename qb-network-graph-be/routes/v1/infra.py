"""Infrastructure metrics endpoint — Redis, Neo4j, Paimon, Elasticsearch, OTEL stats."""
import logging
import time

import httpx
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/infra", tags=["infra"])


def _redis_metrics(redis_client) -> dict:
    """Gather Redis cache stats."""
    if not redis_client:
        return {"status": "unavailable"}
    try:
        info = redis_client.info("stats")
        mem = redis_client.info("memory")
        db_size = redis_client.dbsize()

        # Count keys by prefix pattern
        prefixes = {"entity": 0, "rels": 0, "subgraph": 0, "connections": 0, "search": 0, "traverse": 0}
        for prefix in prefixes:
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{prefix}:*", count=500)
                prefixes[prefix] += len(keys)
                if cursor == 0:
                    break

        return {
            "status": "connected",
            "total_keys": db_size,
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
            "hit_rate": round(
                info.get("keyspace_hits", 0) /
                max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100, 1
            ),
            "memory_used_mb": round(mem.get("used_memory", 0) / 1024 / 1024, 2),
            "memory_peak_mb": round(mem.get("used_memory_peak", 0) / 1024 / 1024, 2),
            "keys_by_type": prefixes,
        }
    except Exception as e:
        logger.warning(f"Redis metrics failed: {e}")
        return {"status": "error", "error": str(e)}


def _neo4j_metrics(driver, database) -> dict:
    """Gather Neo4j node/relationship counts."""
    if not driver:
        return {"status": "unavailable"}
    try:
        with driver.session(database=database) as session:
            result = session.run("""
                MATCH (e:Entity)
                WITH count(e) AS total_entities,
                     count(CASE WHEN e.status = 'ACTIVE' THEN 1 END) AS active_entities,
                     count(CASE WHEN e.status = 'MERGED' THEN 1 END) AS merged_entities
                OPTIONAL MATCH ()-[bf:BUYS_FROM]->()
                WITH total_entities, active_entities, merged_entities, count(bf) AS buys_from
                OPTIONAL MATCH ()-[st:SELLS_TO]->()
                RETURN total_entities, active_entities, merged_entities,
                       buys_from, count(st) AS sells_to
            """).single()

            return {
                "status": "connected",
                "entities": {
                    "total": result["total_entities"],
                    "active": result["active_entities"],
                    "merged": result["merged_entities"],
                },
                "relationships": {
                    "buys_from": result["buys_from"],
                    "sells_to": result["sells_to"],
                    "total": result["buys_from"] + result["sells_to"],
                },
            }
    except Exception as e:
        logger.warning(f"Neo4j metrics failed: {e}")
        return {"status": "error", "error": str(e)}


def _paimon_metrics(paimon_client) -> dict:
    """Gather Paimon warehouse table counts."""
    if not paimon_client or not paimon_client.available:
        return {"status": "unavailable"}
    try:
        tables = {}
        # Simple counts — read_table returns list of dicts
        table_specs = {
            "golden_records": ("gold.golden_records", None),
            "golden_records_active": ("gold.golden_records", {"status": "ACTIVE"}),
            "relationships": ("gold.relationships", None),
            "pending_resolution": ("gold.pending_resolution", None),
            "pending_review": ("gold.pending_resolution", {"status": "PENDING"}),
            "resolution_audit": ("gold.resolution_audit", None),
            "connection_alerts": ("gold.connection_alerts", None),
        }
        for key, (tbl, filters) in table_specs.items():
            try:
                rows = paimon_client.query(tbl, filters=filters)
                tables[key] = len(rows)
            except Exception:
                tables[key] = -1

        return {
            "status": "connected",
            "warehouse": getattr(paimon_client, '_warehouse', 'unknown'),
            "tables": tables,
        }
    except Exception as e:
        logger.warning(f"Paimon metrics failed: {e}")
        return {"status": "error", "error": str(e)}


def _elasticsearch_metrics() -> dict:
    """Gather Elasticsearch cluster and index stats."""
    try:
        with httpx.Client(timeout=3) as client:
            health = client.get("http://localhost:9200/_cluster/health").json()
            indices = client.get("http://localhost:9200/_cat/indices?format=json&h=index,docs.count,store.size").json()

        index_stats = {}
        for idx in indices:
            name = idx.get("index", "")
            if name.startswith("."):
                continue
            index_stats[name] = {
                "docs": int(idx.get("docs.count", 0) or 0),
                "size": idx.get("store.size", "0b"),
            }

        return {
            "status": health.get("status", "unknown"),
            "cluster_name": health.get("cluster_name"),
            "node_count": health.get("number_of_nodes", 0),
            "active_shards": health.get("active_shards", 0),
            "indices": index_stats,
        }
    except Exception as e:
        logger.warning(f"Elasticsearch metrics failed: {e}")
        return {"status": "error", "error": str(e)}


def _kibana_metrics() -> dict:
    """Check Kibana availability."""
    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get("http://localhost:5601/api/status")
            data = resp.json()
        status = data.get("status", {}).get("overall", {})
        return {
            "status": status.get("level", "unknown"),
            "summary": status.get("summary", ""),
            "version": data.get("version", {}).get("number", ""),
        }
    except Exception as e:
        logger.warning(f"Kibana metrics failed: {e}")
        return {"status": "error", "error": str(e)}


def _otel_collector_metrics() -> dict:
    """Check OTEL Collector status and pipeline stats from Elasticsearch indices."""
    result = {
        "status": "error",
        "grpc_port": 4317,
        "http_port": 4318,
        "prometheus_port": 8889,
    }
    try:
        # Verify collector is reachable via its Prometheus metrics endpoint
        with httpx.Client(timeout=3) as client:
            resp = client.get("http://localhost:8889/metrics")
            if resp.status_code == 200:
                result["status"] = "connected"

            # Get trace/log counts from Elasticsearch (the collector's sink)
            try:
                traces = client.get("http://localhost:9200/qb-traces/_count").json()
                logs = client.get("http://localhost:9200/qb-logs/_count").json()
                result["pipeline"] = {
                    "traces_indexed": traces.get("count", 0),
                    "logs_indexed": logs.get("count", 0),
                }
            except Exception:
                result["pipeline"] = {}

    except Exception as e:
        logger.warning(f"OTEL Collector metrics failed: {e}")
        result["error"] = str(e)
    return result


@router.get("/metrics")
def infra_metrics(request: Request):
    """Aggregate infrastructure metrics from all data stores."""
    t0 = time.time()

    neo4j_driver = getattr(request.app.state, "neo4j_driver", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    paimon_client = getattr(request.app.state, "paimon_client", None)
    cfg = getattr(request.app.state, "cfg", None)

    neo4j_db = cfg.neo4j.database if cfg else "neo4j"

    return {
        "redis": _redis_metrics(redis_client),
        "neo4j": _neo4j_metrics(neo4j_driver, neo4j_db),
        "paimon": _paimon_metrics(paimon_client),
        "elasticsearch": _elasticsearch_metrics(),
        "kibana": _kibana_metrics(),
        "otel_collector": _otel_collector_metrics(),
        "duration_ms": round((time.time() - t0) * 1000),
    }
