from typing import List, Optional
from fastapi import APIRouter
from api.api_v1.deps import SessionDep
from core import constants
from models.app_config import AppConfig
from sqlmodel import select

router = APIRouter()


@router.get("/")
def get_apy_config(
    session: SessionDep,
):
    statement = select(AppConfig).where(
        AppConfig.name == constants.AppConfigKey.APY_PERIOD.value
    )
    app_config = session.exec(statement).first()
    return {
        constants.AppConfigKey.APY_PERIOD.value: app_config.key if app_config else 45
    }
