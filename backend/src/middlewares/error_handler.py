"""全局错误处理：统一 {code,message,detail} 响应，前端按 code 恢复。"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.utils.errors import AppError

logger = logging.getLogger("app.errors")


def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """pydantic v2 的 ctx.error 可能是 ValueError 实例，不能直接 JSON 序列化，逐条降级成字符串。"""
    items: list[dict[str, Any]] = []
    for error in exc.errors()[:4]:
        try:
            items.append(
                {
                    "loc": [str(part) for part in error.get("loc", ())],
                    "msg": str(error.get("msg", "")),
                    "type": str(error.get("type", "")),
                }
            )
        except Exception:  # noqa: BLE001 - 兜底：校验错误本身不能再抛错
            items.append({"loc": [], "msg": "参数不合法", "type": "value_error"})
    return items


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "INTERNAL"
        return JSONResponse(status_code=exc.status_code, content={"code": code, "message": str(exc.detail), "detail": None})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION", "message": "请求参数不合法", "detail": _safe_errors(exc)},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"code": "INTERNAL", "message": "服务内部错误", "detail": None})
