from typing import List, Optional
from fastapi import APIRouter
from core.config import settings

router = APIRouter()


@router.get("/")
def get_apy_config():
    return {"apy_period": settings.APY_PERIOD}
