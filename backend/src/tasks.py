"""Celery 任务：心跳、每日 SRM 复算（对运行中的实验重算分流均衡）。"""
from __future__ import annotations

import time

from sqlalchemy import select

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_srm_refresh() -> dict:
    """每天 07:40 对运行中的实验重算 SRM，分流漂移会立刻出现在总览。"""
    from src.config.database import session_scope
    from src.models.experiment import Experiment
    from src.services import audit_service, srm_service
    from src.utils.errors import AppError

    done = 0
    with session_scope() as db:
        experiments = db.scalars(select(Experiment).where(Experiment.status == "running")).all()
        for experiment in experiments:
            try:
                result = srm_service.check(db, experiment)
            except AppError as exc:
                logger.warning("daily srm skip %s: %s", experiment.code, exc.code)
                continue
            done += 1
            audit_service.record(
                db,
                actor_email="scheduler@" + settings.app_name + ".io",
                actor_role="admin",
                action="srm.check",
                entity="experiment",
                entity_id=experiment.id,
                detail={"trigger": "schedule", "chi2": result["chi2"], "alarm": result["alarm"]},
                layer="worker",
            )
    logger.info("daily srm refresh finished: %s experiments", done)
    return {"experiments": done}
