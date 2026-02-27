"""Connection routes: GET /connections/auto, GET /connections/manual, POST /connections.

POST /connections now fires a background task that sends the entity data
to the entity agent for resolution and creates lifecycle alerts.
"""
import logging
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Request

from models.api import AddConnectionRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/connections/auto")
def get_auto_connections(request: Request):
    mysql = request.app.state.mysql
    conns = mysql.get_auto_connections()
    return {"data": conns}


@router.get("/connections/manual")
def get_manual_connections(request: Request):
    mysql = request.app.state.mysql
    conns = mysql.get_manual_connections()
    return {"data": conns}


@router.post("/connections")
async def add_connection(
    request: Request,
    body: AddConnectionRequest,
    background_tasks: BackgroundTasks,
):
    mysql = request.app.state.mysql
    payload = body.model_dump()
    result = mysql.add_connection(payload)
    connection_id = result["id"]

    # Insert "connection_added" alert
    alert_id = f"a-{uuid.uuid4().hex[:8]}"
    entity_name = (body.entity or {}).get("name") if body.entity else body.name
    mysql.insert_alert(
        alert_id=alert_id,
        connection_id=connection_id,
        alert_type="connection_added",
        title="Connection added",
        message=f"{entity_name or 'New connection'} added as {body.connType}. Entity resolution running.",
        entity_name=entity_name,
    )

    # Fire background resolution
    background_tasks.add_task(
        resolve_connection_async, request.app, connection_id, payload,
    )

    return {"data": result}


# ── Background task ──────────────────────────────────────────

async def resolve_connection_async(app, connection_id: str, payload: dict):
    """Build ClassifiedPersona from form fields and POST to entity agent."""
    mysql = app.state.mysql
    http_client = app.state.http_client

    try:
        mysql.update_connection_agent_status(connection_id, "pending")

        # Build ClassifiedPersona dimensions from form fields
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
        }

        resp = await http_client.post("/resolve", json=request_body)
        resp.raise_for_status()
        data = resp.json()

        decision = data.get("decision", "NEW_ENTITY")
        confidence = data.get("confidence", 0.0)
        target_id = data.get("target_golden_record_id")

        mysql.update_connection_agent_status(
            connection_id, "resolved", decision, target_id,
        )

        # Insert resolution alert based on decision
        alert_id = f"a-{uuid.uuid4().hex[:8]}"
        entity_name = payload.get("name") or "Entity"

        if decision == "NEW_ENTITY":
            mysql.insert_alert(
                alert_id=alert_id,
                connection_id=connection_id,
                alert_type="entity_created",
                title="New entity created",
                message=f"{entity_name} was added as a new entity in the knowledge graph.",
                entity_name=entity_name,
                target_entity_id=target_id,
                confidence=confidence,
            )
        elif decision == "MERGE":
            mysql.insert_alert(
                alert_id=alert_id,
                connection_id=connection_id,
                alert_type="entity_merged",
                title="Entity merged",
                message=f"{entity_name} was matched and merged into an existing entity ({int(confidence * 100)}% confidence).",
                entity_name=entity_name,
                target_entity_id=target_id,
                confidence=confidence,
            )
        elif decision == "REVIEW":
            mysql.insert_alert(
                alert_id=alert_id,
                connection_id=connection_id,
                alert_type="merge_review",
                title="Merge review required",
                message=f"{entity_name} has a potential match ({int(confidence * 100)}% confidence) that needs human review.",
                entity_name=entity_name,
                target_entity_id=target_id,
                confidence=confidence,
            )

        logger.info(
            f"Entity agent resolved connection {connection_id}: "
            f"decision={decision} confidence={confidence:.2f} target={target_id}"
        )

    except Exception:
        logger.exception(f"Entity agent resolution failed for connection {connection_id}")
        try:
            mysql.update_connection_agent_status(connection_id, "failed")
        except Exception:
            logger.exception("Failed to update agent_status to 'failed'")
