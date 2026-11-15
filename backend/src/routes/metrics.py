from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import CHECK_ROLES
from src.controllers import metric_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.experiment import MetricCheckIn, SrmCheckIn
from src.utils.pagination import page_params

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def list_metrics(
    experiment_id: int | None = None,
    variant_code: str | None = None,
    significant: bool | None = None,
    q: str | None = None,
    limit: int = Query(40),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return metric_controller.list_metrics(
        db,
        experiment_id=experiment_id,
        variant_code=variant_code,
        significant=significant,
        q=q,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/experiments/{experiment_id}/srm")
def get_srm(
    experiment_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return metric_controller.srm_snapshot(db, experiment_id)


@router.post("/experiments/{experiment_id}/srm-check")
def run_srm(
    experiment_id: int,
    payload: SrmCheckIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*CHECK_ROLES)),
) -> dict:
    return metric_controller.run_srm(db, experiment_id, payload.model_dump(exclude_none=True), principal, request)


@router.post("/experiments/{experiment_id}/metric-tests")
def run_metric_tests(
    experiment_id: int,
    payload: MetricCheckIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*CHECK_ROLES)),
) -> dict:
    return metric_controller.run_metric_tests(db, experiment_id, payload.model_dump(exclude_none=True), principal, request)
