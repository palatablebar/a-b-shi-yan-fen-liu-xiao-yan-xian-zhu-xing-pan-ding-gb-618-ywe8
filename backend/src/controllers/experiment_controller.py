"""实验登记控制器：写操作记领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.constants.roles import DEFAULT_OWNER
from src.services import audit_service, experiment_service


def list_experiments(db: Session, **filters) -> dict:
    return experiment_service.list_experiments(db, **filters)


def get_experiment(db: Session, experiment_id: int) -> dict:
    return experiment_service.detail(db, experiment_id)


def create_experiment(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.create_experiment(db, payload, owner_default=DEFAULT_OWNER)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="experiment.create",
        entity="experiment",
        entity_id=experiment.id,
        detail={
            "code": experiment.code,
            "primary_metric": experiment.primary_metric,
            "variants": [item["code"] for item in payload.get("variants") or []],
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return experiment_service.detail(db, experiment.id)


def update_experiment(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    experiment_service.update_experiment(db, experiment, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="experiment.update",
        entity="experiment",
        entity_id=experiment.id,
        detail={"fields": sorted(payload.keys())},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return experiment_service.detail(db, experiment_id)
