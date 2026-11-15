"""FastAPI 装配：中间件顺序、异常处理、路由挂载、启动钩子。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.database import engine, wait_for_db
from src.config.settings import settings
from src.middlewares.audit_logger import AuditMiddleware
from src.middlewares.auth import AuthMiddleware
from src.middlewares.error_handler import register_exception_handlers
from src.middlewares.rate_limit import RateLimitMiddleware
from src.routes import api_router

logger = logging.getLogger(f"{settings.app_name}.app")


def _bootstrap_database() -> None:
    from src.models import Base  # noqa: WPS433 - 延迟导入避免循环

    wait_for_db()
    Base.metadata.create_all(bind=engine)
    # 已存在的旧库：补投放段相关列/索引（幂等），再回填 baseline 投放段承接存量数据
    from src.config.database import session_scope
    from src.config.migrations import run_compat_migrations
    from src.services.segment_service import ensure_baseline_segments

    run_compat_migrations()
    with session_scope() as db:
        ensure_baseline_segments(db)


def _run_seed_once() -> None:
    if not settings.seed_demo:
        return
    try:
        from scripts.seed_demo import seed_all

        seed_all()
    except Exception as exc:  # noqa: BLE001 - 启动阶段不阻塞
        logger.warning("[SEED_DEMO] seed failed (ignored): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_database()
    _run_seed_once()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_title, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    register_exception_handlers(app)

    app.include_router(api_router, prefix="/api")
    app.include_router(api_router, include_in_schema=False)
    return app
