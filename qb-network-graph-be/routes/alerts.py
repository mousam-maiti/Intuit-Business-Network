"""Alert routes: GET /alerts, POST /alerts/{alert_id}/dismiss."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/alerts")
def get_alerts(request: Request):
    mysql = request.app.state.mysql
    alerts = mysql.get_alerts()
    return {"data": alerts}


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str, request: Request):
    mysql = request.app.state.mysql
    mysql.dismiss_alert(alert_id)
    return {"data": {"dismissed": True}}
