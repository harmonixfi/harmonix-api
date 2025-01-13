from typing import List, Optional
from fastapi import APIRouter
from api.api_v1.deps import SessionDep
from models.app_config import AppConfig
from sqlmodel import select

router = APIRouter()


@router.get("/")
def get_apy_config(
    session: SessionDep,
):
    statement = select(AppConfig).where(AppConfig.key == "apy_period")
    app_config = session.exec(statement).first()
    return {"apy_period": app_config.key if app_config else 15}
