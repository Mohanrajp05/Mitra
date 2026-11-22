
from fastapi import APIRouter, Depends

from app.core.metrics import get_metrics
from app.core.security import get_current_user

router = APIRouter(prefix="/api/ops", tags=["Operations"])


@router.get("/metrics")
def operational_metrics(current_user: dict = Depends(get_current_user)):
    return get_metrics().snapshot()
