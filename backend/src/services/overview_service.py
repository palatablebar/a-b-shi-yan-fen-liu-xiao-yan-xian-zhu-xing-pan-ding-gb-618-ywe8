"""总览：实验台账计数、SRM 告警、显著指标、待决策、样本趋势、worker 心跳。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    EXPERIMENT_STATUS_LABELS,
    METRIC_LABELS,
    SRM_STATUS_LABELS,
    VERDICT_LABELS,
)
from src.models.assignment import Assignment
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.models.metric_result import MetricResult
from src.utils.timeutil import iso_date, local_now, utcnow


def worker_alive() -> bool:
    try:
        import redis
        import time

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def overview(db: Session) -> dict:
    experiments_total = db.scalar(select(func.count()).select_from(Experiment)) or 0
    running_total = (
        db.scalar(select(func.count()).select_from(Experiment).where(Experiment.status == "running")) or 0
    )
    srm_alarm_total = (
        db.scalar(select(func.count()).select_from(Experiment).where(Experiment.has_srm_alarm.is_(True))) or 0
    )
    metric_total = db.scalar(select(func.count()).select_from(MetricResult)) or 0
    significant_total = (
        db.scalar(select(func.count()).select_from(MetricResult).where(MetricResult.significant.is_(True))) or 0
    )
    decided_total = db.scalar(select(func.count()).select_from(Decision)) or 0
    pending_total = max(0, experiments_total - decided_total)

    status_rows = db.execute(select(Experiment.status, func.count()).group_by(Experiment.status)).all()
    status_map = dict(status_rows)
    verdict_rows = db.execute(select(Decision.verdict, func.count()).group_by(Decision.verdict)).all()
    srm_rows = db.execute(select(Experiment.srm_status, func.count()).group_by(Experiment.srm_status)).all()

    alarm_experiments = db.scalars(
        select(Experiment).where(Experiment.has_srm_alarm.is_(True)).order_by(Experiment.srm_p_value)
    ).all()

    significant_rows = db.scalars(
        select(MetricResult)
        .where(MetricResult.significant.is_(True))
        .order_by(MetricResult.q_value, MetricResult.lift.desc())
        .limit(6)
    ).all()
    experiment_codes = {
        item.id: (item.code, item.name)
        for item in db.scalars(
            select(Experiment).where(Experiment.id.in_([row.experiment_id for row in significant_rows]))
        ).all()
    } if significant_rows else {}

    latest_date = db.scalar(select(func.max(Assignment.stat_date)))
    trend = []
    if latest_date is not None:
        start = latest_date - timedelta(days=6)
        rows = db.execute(
            select(
                Assignment.stat_date,
                func.coalesce(func.sum(Assignment.samples), 0),
                func.coalesce(func.sum(Assignment.conversions), 0),
            )
            .where(Assignment.stat_date >= start, Assignment.stat_date <= latest_date)
            .group_by(Assignment.stat_date)
            .order_by(Assignment.stat_date)
        ).all()
        by_date = {row[0]: (int(row[1]), int(row[2])) for row in rows}
        for offset in range(6, -1, -1):
            day = latest_date - timedelta(days=offset)
            samples, conversions = by_date.get(day, (0, 0))
            trend.append(
                {
                    "date": iso_date(day),
                    "samples": samples,
                    "conversions": conversions,
                    "rate": round(conversions / samples, 5) if samples else 0.0,
                }
            )

    latest_metrics = db.scalars(
        select(MetricResult).order_by(MetricResult.computed_at.desc(), MetricResult.id.desc()).limit(5)
    ).all()

    return {
        "experiments_total": experiments_total,
        "running_total": running_total,
        "srm_alarm_total": srm_alarm_total,
        "metric_total": metric_total,
        "significant_total": significant_total,
        "decided_total": decided_total,
        "pending_total": pending_total,
        "sample_total": db.scalar(select(func.coalesce(func.sum(Assignment.samples), 0))) or 0,
        "assignment_rows": db.scalar(select(func.count()).select_from(Assignment)) or 0,
        "worker_alive": worker_alive(),
        "generated_at": utcnow().isoformat(timespec="seconds") + "Z",
        "anchor_date": iso_date(latest_date),
        "status_breakdown": [
            {
                "key": key,
                "label": EXPERIMENT_STATUS_LABELS.get(key, key),
                "count": int(status_map.get(key, 0)),
            }
            for key in ("running", "paused", "draft", "finished", "archived")
        ],
        "verdict_breakdown": [
            {
                "key": key,
                "label": VERDICT_LABELS.get(key, key),
                "count": int(dict(verdict_rows).get(key, 0)),
            }
            for key in ("ship", "continue", "stop")
        ],
        "srm_breakdown": [
            {
                "key": key,
                "label": SRM_STATUS_LABELS.get(key, key),
                "count": int(dict(srm_rows).get(key, 0)),
            }
            for key in ("balanced", "srm", "unknown")
        ],
        "srm_alarms": [
            {
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "chi2": item.srm_chi2,
                "df": item.srm_df,
                "p_value": item.srm_p_value,
                "status_label": SRM_STATUS_LABELS.get(item.srm_status, item.srm_status),
                "primary_metric_label": METRIC_LABELS.get(item.primary_metric, item.primary_metric),
                "cells": (item.srm_payload or {}).get("cells", []),
            }
            for item in alarm_experiments
        ],
        "significant": [
            {
                "id": row.id,
                "experiment_id": row.experiment_id,
                "experiment_code": experiment_codes.get(row.experiment_id, ("", ""))[0],
                "experiment_name": experiment_codes.get(row.experiment_id, ("", ""))[1],
                "metric_name": row.metric_name,
                "variant_code": row.variant_code,
                "lift": row.lift,
                "p_value": row.p_value,
                "q_value": row.q_value,
                "method": row.method,
                "verdict": row.verdict,
                "verdict_label": VERDICT_LABELS.get(row.verdict, row.verdict),
            }
            for row in significant_rows
        ],
        "latest_metrics": [
            {
                "id": row.id,
                "experiment_id": row.experiment_id,
                "metric_name": row.metric_name,
                "variant_code": row.variant_code,
                "q_value": row.q_value,
                "lift": row.lift,
                "significant": row.significant,
                "computed_at": row.computed_at.isoformat(timespec="seconds") + "Z" if row.computed_at else None,
            }
            for row in latest_metrics
        ],
        "trend": trend,
        "local_today": local_now().date().isoformat(),
    }


def decision_summary(db: Session) -> list[dict]:
    rows = db.execute(
        select(Decision.verdict, func.count()).group_by(Decision.verdict).order_by(Decision.verdict)
    ).all()
    return [{"key": key, "label": VERDICT_LABELS.get(key, key), "count": int(count)} for key, count in rows]
