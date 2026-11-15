"""分流样本控制器：列表 / 渠道矩阵 / 录入。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import assignment_service, audit_service, experiment_service


def list_assignments(db: Session, experiment_id: int, **filters) -> dict:
    experiment_service.get_experiment(db, experiment_id)
    return assignment_service.list_assignments(db, experiment_id, **filters)


def matrix(db: Session, experiment_id: int, metric_key: str | None = None) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    variants = experiment_service.get_variants(db, experiment_id)
    return {
        "experiment": experiment_service.serialize(experiment, variants=variants),
        "totals": assignment_service.variant_totals(db, experiment, metric_key),
        "matrix": assignment_service.channel_matrix(db, experiment, metric_key),
        "daily": assignment_service.daily_series(db, experiment, metric_key),
        "metric_keys": assignment_service.metric_keys(db, experiment_id),
    }


def create_assignment(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    row = assignment_service.create_assignment(db, experiment, payload, operator_email=principal["email"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="assignment.create",
        entity="assignment",
        entity_id=row.id,
        detail={
            "experiment": experiment.code,
            "variant": payload["variant_code"],
            "channel": payload["channel"],
            "metric": payload["metric_key"],
            "samples": row.samples,
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return assignment_service.serialize(row)
