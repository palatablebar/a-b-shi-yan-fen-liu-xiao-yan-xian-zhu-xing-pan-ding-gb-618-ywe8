"""算法控制器：SRM 校验（算法 A）与指标检验（算法 B）。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, experiment_service, metric_service, srm_service


def list_metrics(db: Session, **filters) -> dict:
    return metric_service.list_metrics(db, **filters)


def srm_snapshot(db: Session, experiment_id: int) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    return srm_service.snapshot(experiment)


def run_srm(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    result = srm_service.check(
        db,
        experiment,
        alpha=payload.get("alpha"),
        power=payload.get("power"),
        alarm_p=payload.get("alarm_p"),
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="srm.check",
        entity="experiment",
        entity_id=experiment.id,
        detail={
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
    result = metric_service.run_checks(
        db,
        experiment,
        method=payload.get("method") or "bh",
        alpha=payload.get("alpha"),
        variant_code=payload.get("variant_code"),
        operator_email=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="metric.check",
        entity="experiment",
        entity_id=experiment.id,
        detail={
            "method": result["method"],
            "total": result["total"],
            "significant": sum(item["significant_count"] for item in result["results"]),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result
