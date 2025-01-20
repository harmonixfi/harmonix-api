from fastapi import APIRouter

from api.api_v1.endpoints import (
    vaults,
    portfolio,
    statistics,
    referral,
    partners,
    healthz,
    reports,
    configs,
    earning_page,
)

api_router = APIRouter()

# Group routes by adding tags parameter
api_router.include_router(vaults.router, prefix="/vaults", tags=["Vaults"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(statistics.router, prefix="/statistics", tags=["Statistics"])
api_router.include_router(referral.router, prefix="/referral", tags=["Referral"])
api_router.include_router(partners.router, prefix="/partners", tags=["Partners"])
api_router.include_router(healthz.router, prefix="/healthz", tags=["Others"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(configs.router, prefix="/app-config", tags=["App Configs"])
api_router.include_router(earning_page.router, prefix="/earning", tags=["Earning Page"])
api_router.redirect_slashes = False
