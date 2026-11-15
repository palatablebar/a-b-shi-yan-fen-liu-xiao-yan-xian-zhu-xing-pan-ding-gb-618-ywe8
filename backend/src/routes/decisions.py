from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import DECISION_ROLES
from src.controllers import decision_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.decision import DecisionIn
from src.utils.pagination import page_params

router = APIRouter(tags=["decisions"])


@router.get("/decisions")
def list_decisions(
    verdict: str | None = None,
    q: str | None = None,
    limit: int = Query(40),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return decision_controller.list_decisions(db, verdict=verdict, q=q, limit=page.limit, offset=page.offset)


@router.post("/experiments/{experiment_id}/decisions", status_code=201)
def create_decision(
    experiment_id: int,
    payload: DecisionIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*DECISION_ROLES)),
) -> dict:
    return decision_controller.create_decision(db, experiment_id, payload.model_dump(), principal, request)
