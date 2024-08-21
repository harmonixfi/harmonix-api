from fastapi import APIRouter, FastAPI, status
from pydantic import BaseModel

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str


@router.get("/", response_model=HealthCheckResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthCheckResponse(status="ok")
