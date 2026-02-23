"""
Milvus client — vector search store for golden records.

Written by entity_writer on every golden record mutation (Pattern A: immediate sync).
Read by UI search bar (multi-vector hybrid search) and agent semantic search.

Embedding strategy:
  Primary: Google Gemini text-embedding-004 (768d, output_dimensionality supported)
  Fallback: sentence-transformers/all-MiniLM-L6-v2 (384d, local CPU)

Collection schema (4 vector fields — Milvus v2.4 limit):
  name_embedding:       FloatVector[128]
  industry_vector:      FloatVector[64]
  commodity_vector:     FloatVector[64]
  composite_vector:     FloatVector[256]   (single embedding of all dimensions incl. location + behavioral)
  Scalar fields: golden_record_id, state, naics_prefix, confidence, entity_type
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

from config import MilvusConfig

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_LOCAL_MODEL = True
except ImportError:
    HAS_LOCAL_MODEL = False

try:
    from pymilvus import (
        connections, Collection, CollectionSchema, FieldSchema,
        DataType, utility,
    )
    HAS_MILVUS = True
except ImportError:
    HAS_MILVUS = False

DIMS = {
    "name_embedding": 128,
    "industry_vector": 64,
    "commodity_vector": 64,
    "composite_vector": 256,
}

COLLECTION_NAME = "golden_records"


class MilvusClient:
    """Milvus vector store client for golden record search.

    Falls back to in-memory list if Milvus/embedding unavailable.
    """

    def __init__(self, cfg: MilvusConfig):
        self._cfg = cfg
        self._collection: Optional[Collection] = None
        self._using_mock = False
        self._embed_provider = None
        self._local_model = None
        self._mock_vectors: dict[str, dict] = {}

    async def connect(self):
        self._setup_embeddings()

        if not HAS_MILVUS:
            logger.warning("pymilvus not installed — using in-memory fallback")
            self._using_mock = True
            return

        try:
            connections.connect(alias="default", host=self._cfg.host, port=self._cfg.port)
            self._ensure_collection()
            logger.info(f"Milvus connected: {self._cfg.host}:{self._cfg.port}, "
                        f"embed={self._embed_provider}")
        except Exception as e:
            logger.warning(f"Milvus connection failed ({e}) — using in-memory fallback")
            self._using_mock = True

    def _setup_embeddings(self):
        gemini_key = self._cfg.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if HAS_GEMINI and gemini_key:
            genai.configure(api_key=gemini_key)
            self._embed_provider = "gemini"
        elif HAS_LOCAL_MODEL:
            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
            self._embed_provider = "local"
        else:
            self._embed_provider = "none"
            logger.warning("No embedding provider — vectors will be zero-filled")

    def _ensure_collection(self):
        if utility.has_collection(COLLECTION_NAME):
            self._collection = Collection(COLLECTION_NAME)
            self._collection.load()
            return

        fields = [
            FieldSchema("golden_record_id", DataType.VARCHAR, max_length=36, is_primary=True),
            FieldSchema("canonical_name", DataType.VARCHAR, max_length=255),
            FieldSchema("name_embedding", DataType.FLOAT_VECTOR, dim=DIMS["name_embedding"]),
            FieldSchema("industry_vector", DataType.FLOAT_VECTOR, dim=DIMS["industry_vector"]),
            FieldSchema("commodity_vector", DataType.FLOAT_VECTOR, dim=DIMS["commodity_vector"]),
            FieldSchema("composite_vector", DataType.FLOAT_VECTOR, dim=DIMS["composite_vector"]),
            FieldSchema("state", DataType.VARCHAR, max_length=2),
            FieldSchema("naics_prefix", DataType.VARCHAR, max_length=4),
            FieldSchema("confidence", DataType.FLOAT),
            FieldSchema("entity_type", DataType.VARCHAR, max_length=15),
            FieldSchema("source_count", DataType.INT64),
        ]
        schema = CollectionSchema(fields, "Golden record persona vectors")
        self._collection = Collection(COLLECTION_NAME, schema)

        for vec_field, dim in DIMS.items():
            nlist = max(16, min(1024, dim * 4))
            self._collection.create_index(
                vec_field,
                {"metric_type": "COSINE", "index_type": "IVF_SQ8", "params": {"nlist": nlist}},
            )
        self._collection.load()
        logger.info(f"Milvus collection '{COLLECTION_NAME}' created")

    # ── Embedding ────────────────────────────────────────────

    def _embed_text(self, text: str, target_dim: int) -> list[float]:
        if not text or not text.strip():
            return [0.0] * target_dim
        if self._embed_provider == "gemini":
            return self._embed_gemini(text, target_dim)
        elif self._embed_provider == "local":
            return self._embed_local(text, target_dim)
        return [0.0] * target_dim

    def _embed_gemini(self, text: str, target_dim: int) -> list[float]:
        try:
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text,
                task_type="SEMANTIC_SIMILARITY",
                output_dimensionality=target_dim,
            )
            vec = result["embedding"]
            return (vec[:target_dim] if len(vec) >= target_dim
                    else vec + [0.0] * (target_dim - len(vec)))
        except Exception as e:
            logger.warning(f"Gemini embedding failed: {e}")
            return self._embed_local(text, target_dim) if self._local_model else [0.0] * target_dim

    def _embed_local(self, text: str, target_dim: int) -> list[float]:
        if not self._local_model:
            return [0.0] * target_dim
        try:
            vec = self._local_model.encode(text, normalize_embeddings=True).tolist()
            return vec[:target_dim] if len(vec) >= target_dim else vec + [0.0] * (target_dim - len(vec))
        except Exception:
            return [0.0] * target_dim

    def _build_texts_from_persona(self, gr_data: dict) -> dict:
        persona = gr_data.get("persona", {})
        if isinstance(persona, str):
            try:
                persona = json.loads(persona)
            except (json.JSONDecodeError, TypeError):
                persona = {}

        identity = persona.get("identity", {})
        industry = persona.get("industry", {})
        location = persona.get("location", {})
        commodity = persona.get("commodity", {})
        behavioral = persona.get("behavioral", {})

        # Name: canonical + variants
        name_parts = [gr_data.get("canonical_name", "")]
        variants = gr_data.get("name_variants", [])
        if isinstance(variants, str):
            try: variants = json.loads(variants)
            except: variants = []
        name_parts.extend(variants[:5])

        # Industry
        industry_parts = [industry.get("original_category", ""), industry.get("naics_code", "")]

        # Commodity
        keywords = commodity.get("top_keywords", [])
        if isinstance(keywords, str):
            try: keywords = json.loads(keywords)
            except: keywords = []
        svc_cats = commodity.get("service_categories", [])
        if isinstance(svc_cats, str):
            try: svc_cats = json.loads(svc_cats)
            except: svc_cats = []

        # Location
        loc_parts = [
            location.get("city_norm", "") or gr_data.get("city", ""),
            location.get("state", "") or gr_data.get("state", ""),
            location.get("zip5", "") or gr_data.get("zip5", ""),
        ]

        # Behavioral
        behav_parts = [behavioral.get("volume_bracket", "") or gr_data.get("volume_bracket", "")]
        avg_txn = behavioral.get("avg_transaction") or gr_data.get("avg_transaction")
        if avg_txn:
            behav_parts.append(f"average transaction {avg_txn}")

        return {
            "name": " ".join(set(filter(None, name_parts))),
            "industry": " ".join(filter(None, industry_parts)),
            "commodity": " ".join(keywords + svc_cats),
            "location": " ".join(filter(None, loc_parts)),
            "behavioral": " ".join(filter(None, behav_parts)),
        }

    def _compute_vectors(self, gr_data: dict) -> dict:
        texts = self._build_texts_from_persona(gr_data)
        name_vec = self._embed_text(texts["name"], DIMS["name_embedding"])
        industry_vec = self._embed_text(texts["industry"], DIMS["industry_vector"])
        commodity_vec = self._embed_text(texts["commodity"], DIMS["commodity_vector"])

        # Composite: embed combined text from all dimensions (incl. location + behavioral)
        composite_text = " ".join(filter(None, [
            texts["name"], texts["industry"], texts["commodity"],
            texts["location"], texts["behavioral"],
        ]))
        composite_vec = self._embed_text(composite_text, DIMS["composite_vector"])

        return {
            "name_embedding": name_vec,
            "industry_vector": industry_vec,
            "commodity_vector": commodity_vec,
            "composite_vector": composite_vec,
        }

    # ── Write ────────────────────────────────────────────────

    def upsert_golden_record(self, gr_data: dict) -> dict:
        gr_id = gr_data.get("golden_record_id", "")
        vectors = self._compute_vectors(gr_data)

        persona = gr_data.get("persona", {})
        if isinstance(persona, str):
            try: persona = json.loads(persona)
            except: persona = {}

        naics = (persona.get("industry", {}).get("naics_code", "") or
                 gr_data.get("naics_code", "") or "")

        record = {
            "golden_record_id": gr_id,
            "canonical_name": (gr_data.get("canonical_name", "") or "")[:255],
            "state": (gr_data.get("state", "") or "")[:2],
            "naics_prefix": naics[:4] if naics else "",
            "confidence": float(gr_data.get("confidence", 0.0)),
            "entity_type": (gr_data.get("entity_type", "PHANTOM") or "PHANTOM")[:15],
            "source_count": int(gr_data.get("source_count", 1)),
            **vectors,
        }

        if self._using_mock:
            self._mock_vectors[gr_id] = record
            return {"success": True, "provider": self._embed_provider, "mock": True}

        try:
            self._collection.upsert([record])
            return {"success": True, "provider": self._embed_provider}
        except Exception as e:
            logger.error(f"Milvus upsert failed for {gr_id}: {e}")
            return {"success": False, "error": str(e)}

    def delete_golden_record(self, golden_record_id: str) -> bool:
        if self._using_mock:
            self._mock_vectors.pop(golden_record_id, None)
            return True
        try:
            self._collection.delete(f'golden_record_id == "{golden_record_id}"')
            return True
        except Exception as e:
            logger.error(f"Milvus delete failed: {e}")
            return False

    # ── Search ───────────────────────────────────────────────

    def search_by_text(self, query_text: str, state_filter: str = None,
                       naics_filter: str = None, top_k: int = 10) -> list[dict]:
        query_vec = self._embed_text(query_text, DIMS["composite_vector"])

        if self._using_mock:
            return list(self._mock_vectors.values())[:top_k]

        filters = []
        if state_filter: filters.append(f'state == "{state_filter}"')
        if naics_filter: filters.append(f'naics_prefix == "{naics_filter[:4]}"')
        expr = " and ".join(filters) if filters else ""

        try:
            results = self._collection.search(
                data=[query_vec], anns_field="composite_vector",
                param={"metric_type": "COSINE", "params": {"nprobe": 32}},
                limit=top_k, expr=expr or None,
                output_fields=["golden_record_id", "canonical_name", "state",
                               "naics_prefix", "confidence", "entity_type"],
            )
            return [{"golden_record_id": h.entity.get("golden_record_id"),
                     "canonical_name": h.entity.get("canonical_name"),
                     "state": h.entity.get("state"),
                     "similarity": h.distance} for h in results[0]]
        except Exception as e:
            logger.error(f"Milvus search failed: {e}")
            return []

    def search_hybrid(self, name_text: str = "", industry_text: str = "",
                      commodity_text: str = "", state_filter: str = None,
                      naics_filter: str = None, top_k: int = 10,
                      weights: dict = None) -> list[dict]:
        if weights is None:
            weights = {"name": 0.40, "industry": 0.30, "commodity": 0.30}

        if self._using_mock:
            return list(self._mock_vectors.values())[:top_k]

        filters = []
        if state_filter: filters.append(f'state == "{state_filter}"')
        if naics_filter: filters.append(f'naics_prefix == "{naics_filter[:4]}"')
        expr = " and ".join(filters) if filters else ""

        try:
            from pymilvus import AnnSearchRequest, WeightedRanker
            requests, weight_values = [], []

            if name_text:
                requests.append(AnnSearchRequest(
                    data=[self._embed_text(name_text, DIMS["name_embedding"])],
                    anns_field="name_embedding",
                    param={"metric_type": "COSINE", "params": {"nprobe": 32}},
                    limit=top_k, expr=expr or None))
                weight_values.append(weights.get("name", 0.4))

            if industry_text:
                requests.append(AnnSearchRequest(
                    data=[self._embed_text(industry_text, DIMS["industry_vector"])],
                    anns_field="industry_vector",
                    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=top_k, expr=expr or None))
                weight_values.append(weights.get("industry", 0.3))

            if commodity_text:
                requests.append(AnnSearchRequest(
                    data=[self._embed_text(commodity_text, DIMS["commodity_vector"])],
                    anns_field="commodity_vector",
                    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=top_k, expr=expr or None))
                weight_values.append(weights.get("commodity", 0.3))

            if not requests:
                return []

            results = self._collection.hybrid_search(
                reqs=requests, ranker=WeightedRanker(*weight_values), limit=top_k,
                output_fields=["golden_record_id", "canonical_name", "state",
                               "naics_prefix", "confidence"])

            return [{"golden_record_id": h.entity.get("golden_record_id"),
                     "canonical_name": h.entity.get("canonical_name"),
                     "similarity": h.distance} for h in results[0]]
        except ImportError:
            return self.search_by_text(f"{name_text} {industry_text} {commodity_text}",
                                       state_filter, naics_filter, top_k)
        except Exception as e:
            logger.error(f"Milvus hybrid search failed: {e}")
            return []

    def bulk_upsert(self, records: list[dict]) -> dict:
        """Bulk upsert for cold start from MySQL backfill."""
        if not records:
            return {"success": True, "count": 0}
        inserted = 0
        for gr_data in records:
            result = self.upsert_golden_record(gr_data)
            if result.get("success"):
                inserted += 1
        if not self._using_mock and self._collection:
            self._collection.flush()
        return {"success": True, "count": inserted}

    # ── Lifecycle ────────────────────────────────────────────

    async def close(self):
        if HAS_MILVUS and not self._using_mock:
            try: connections.disconnect("default")
            except: pass

    @property
    def using_mock(self) -> bool:
        return self._using_mock

    @property
    def entity_count(self) -> int:
        if self._using_mock:
            return len(self._mock_vectors)
        try: return self._collection.num_entities
        except: return 0

    @property
    def embed_provider(self) -> str:
        return self._embed_provider
