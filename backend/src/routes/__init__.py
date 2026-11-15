"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.decisions import router as decisions_router
from src.routes.experiments import router as experiments_router
from src.routes.exports import router as exports_router
from src.routes.health import router as health_router
from src.routes.metrics import router as metrics_router
from src.routes.overview import router as overview_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(experiments_router)
api_router.include_router(metrics_router)
api_router.include_router(decisions_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)
