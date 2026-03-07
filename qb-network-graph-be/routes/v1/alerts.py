"""Alert routes: GET /alerts, POST /alerts/{alert_id}/dismiss."""
from fastapi import APIRouter, Depends

from dependencies import get_alert_service
from services.alert_service import AlertService

router = APIRouter()


@router.get("/alerts")
def get_alerts(svc: AlertService = Depends(get_alert_service)):
    return svc.get_all()


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str, svc: AlertService = Depends(get_alert_service)):
    return svc.dismiss(alert_id)
