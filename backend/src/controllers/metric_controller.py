"""算法控制器：SRM 校验（算法 A）与指标检验（算法 B），均按投放段隔离。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, experiment_service, metric_service, segment_service, srm_service


def list_metrics(db: Session, **filters) -> dict:
    return metric_service.list_metrics(db, **filters)


def srm_snapshot(db: Session, experiment_id: int, segment_id: int | None = None) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    segment = (
        segment_service.get_segment(db, segment_id)
        if segment_id
        else segment_service.active_segment(db, experiment_id)
    )
    return srm_service.snapshot(experiment, db=db, segment=segment)


def run_srm(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    segment = (
        segment_service.get_segment(db, payload["segment_id"])
        if payload.get("segment_id")
        else segment_service.active_segment(db, experiment_id)
    )
    if segment is None:
        from src.utils.errors import AppError

        raise AppError("NO_ACTIVE_SEGMENT", 409, {"reason": "实验还没有生效投放段", "experiment": experiment.code})
    result = srm_service.check(
        db,
        experiment,
        alpha=payload.get("alpha"),
        power=payload.get("power"),
        alarm_p=payload.get("alarm_p"),
        segment=segment,
        operator_email=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="srm.check",
        entity="experiment",
        entity_id=experiment.id,
        detail={
            "segment": segment.segment_code,
            "chi2": result["chi2"],
            "p_value": result["p_value"],
            "alarm": result["alarm"],
            "required_per_variant": result["required_per_variant"],
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result


def run_metric_tests(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    segment = (
        segment_service.get_segment(db, payload["segment_id"])
        if payload.get("segment_id")
        else segment_service.active_segment(db, experiment_id)
    )
    if segment is None:
        from src.utils.errors import AppError

        raise AppError("NO_ACTIVE_SEGMENT", 409, {"reason": "实验还没有生效投放段", "experiment": experiment.code})
    result = metric_service.run_checks(
        db,
        experiment,
        method=payload.get("method") or "bh",
        alpha=payload.get("alpha"),
        variant_code=payload.get("variant_code"),
        operator_email=principal["email"],
        segment=segment,
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="metric.check",
        entity="experiment",
        entity_id=experiment.id,
        detail={
            "segment": segment.segment_code,
            "method": result["method"],
            "total": result["total"],
            "significant": sum(item["significant_count"] for item in result["results"]),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result
