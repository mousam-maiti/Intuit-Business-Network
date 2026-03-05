"""Connection service — auto/manual connections with background resolution."""
from __future__ import annotations

import logging
import re
import uuid

from repositories.base import AbstractConnectionRepository, AbstractAlertRepository

logger = logging.getLogger(__name__)


class ConnectionService:
    def __init__(
        self,
        connection_repo: AbstractConnectionRepository,
        alert_repo: AbstractAlertRepository,
    ):
        self._repo = connection_repo
        self._alert_repo = alert_repo

    def get_auto(self) -> dict:
        return {"data": self._repo.get_auto()}

    def get_manual(self) -> dict:
        return {"data": self._repo.get_manual()}

    def add(self, payload: dict) -> dict:
        result = self._repo.add(payload)
        connection_id = result["id"]

        alert_id = f"a-{uuid.uuid4().hex[:8]}"
        entity_name = (payload.get("entity") or {}).get("name") if payload.get("entity") else payload.get("name")
        self._alert_repo.insert(
            alert_id=alert_id,
            connection_id=connection_id,
            alert_type="connection_added",
            title="Connection added",
            message=f"{entity_name or 'New connection'} added as {payload.get('connType', 'vendor')}. Entity resolution running.",
            entity_name=entity_name,
        )
        return result

    async def resolve_async(self, app, connection_id: str, payload: dict):
        """Background task: build ClassifiedPersona and POST to entity agent."""
        http_client = app.state.http_client

        try:
            self._repo.update_agent_status(connection_id, "pending")

            name = payload.get("name") or ""
            ein_raw = payload.get("ein") or ""
            email = payload.get("email") or ""
            phone_raw = payload.get("phone") or ""
            city = payload.get("city") or ""
            state = payload.get("state") or ""
            zip_code = payload.get("zip") or ""
            commodity = payload.get("commodity") or ""

            ein_clean = re.sub(r"\D", "", ein_raw)
            phone_digits = re.sub(r"\D", "", phone_raw)
            email_domain = email.split("@")[-1] if "@" in email else ""
            zip5 = zip_code[:5] if zip_code else ""
            zip3 = zip_code[:3] if zip_code else ""
            top_keywords = [kw.strip() for kw in commodity.split(",") if kw.strip()][:3]

            classified_persona = {
                "identity": {
                    "normalized_name": name.upper(),
                    "name_first_token": name.split()[0].upper() if name.strip() else "",
                    "ein_clean": ein_clean or None,
                    "phone_digits": phone_digits or None,
                    "email": email or None,
                    "email_domain": email_domain or None,
                },
                "industry": {
                    "original_category": payload.get("category"),
                },
                "location": {
                    "state": state.upper() if state else "",
                    "city_norm": city.upper() if city else None,
                    "zip5": zip5 or None,
                    "zip3": zip3 or None,
                },
                "commodity": {
                    "top_keywords": top_keywords,
                },
                "behavioral": {
                    "payment_terms": payload.get("paymentTerms"),
                },
            }

            event_id = f"conn-{connection_id}"
            record_id = f"manual-{connection_id}"
            request_body = {
                "event_id": event_id,
                "record_id": record_id,
                "record_type": payload.get("connType", "vendor"),
                "company_id": 1,
                "classified_persona": classified_persona,
                "fast_mode": True,
            }

            # ── Two-pass: fast deterministic first, full if ambiguous ──
            resp = await http_client.post("/api/v1/resolve", json=request_body)
            resp.raise_for_status()
            data = resp.json()

            if data.get("decision") == "REVIEW" and data.get("agent_metadata", {}).get("fast_mode_deferred"):
                logger.info(f"Fast pass deferred connection {connection_id} — retrying with full resolution")
                request_body["fast_mode"] = False
                resp = await http_client.post("/api/v1/resolve", json=request_body)
                resp.raise_for_status()
                data = resp.json()

            decision = data.get("decision", "NEW_ENTITY")
            confidence = data.get("confidence", 0.0)
            target_id = data.get("target_golden_record_id")

            self._repo.update_agent_status(connection_id, "resolved", decision, target_id)

            alert_id = f"a-{uuid.uuid4().hex[:8]}"
            entity_name = payload.get("name") or "Entity"

            if decision == "NEW_ENTITY":
                self._alert_repo.insert(
                    alert_id=alert_id, connection_id=connection_id,
                    alert_type="entity_created", title="New entity created",
                    message=f"{entity_name} was added as a new entity in the knowledge graph.",
                    entity_name=entity_name, target_entity_id=target_id, confidence=confidence,
                )
            elif decision == "MERGE":
                self._alert_repo.insert(
                    alert_id=alert_id, connection_id=connection_id,
                    alert_type="entity_merged", title="Entity merged",
                    message=f"{entity_name} was matched and merged into an existing entity ({int(confidence * 100)}% confidence).",
                    entity_name=entity_name, target_entity_id=target_id, confidence=confidence,
                )
            elif decision == "REVIEW":
                self._alert_repo.insert(
                    alert_id=alert_id, connection_id=connection_id,
                    alert_type="merge_review", title="Merge review required",
                    message=f"{entity_name} has a potential match ({int(confidence * 100)}% confidence) that needs human review.",
                    entity_name=entity_name, target_entity_id=target_id, confidence=confidence,
                )

            logger.info(
                f"Entity agent resolved connection {connection_id}: "
                f"decision={decision} confidence={confidence:.2f} target={target_id}"
            )

        except Exception:
            logger.exception(f"Entity agent resolution failed for connection {connection_id}")
            try:
                self._repo.update_agent_status(connection_id, "failed")
            except Exception:
                logger.exception("Failed to update agent_status to 'failed'")
