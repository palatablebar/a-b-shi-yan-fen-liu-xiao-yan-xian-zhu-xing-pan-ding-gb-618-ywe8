"""决策控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, decision_service, experiment_service


def list_decisions(db: Session, **filters) -> dict:
    return decision_service.list_decisions(db, **filters)


def create_decision(db: Session, experiment_id: int, payload: dict, principal: dict, request: Request) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    decision = decision_service.create(db, experiment, payload, decided_by=principal["email"])
    experiment.status = "finished"
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="decision.create",
        entity="decision",
        entity_id=decision.id,
        detail={"experiment": experiment.code, "verdict": decision.verdict},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return decision_service.serialize(decision, experiment)
