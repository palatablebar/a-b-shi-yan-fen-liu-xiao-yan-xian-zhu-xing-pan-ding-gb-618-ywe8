from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import SEGMENT_WRITE_ROLES
from src.controllers import segment_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.segment import SegmentCutoverIn, SegmentRegisterIn

router = APIRouter(tags=["segments"])


@router.get("/experiments/{experiment_id}/segments")
def list_segments(
    experiment_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return segment_controller.list_segments(db, experiment_id)


@router.post("/experiments/{experiment_id}/segments", status_code=201)
def register_content(
    experiment_id: int,
    payload: SegmentRegisterIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*SEGMENT_WRITE_ROLES)),
) -> dict:
    return segment_controller.register_content(db, experiment_id, payload.model_dump(), principal, request)


@router.post("/experiments/{experiment_id}/segments/cutover")
def cutover_segment(
    experiment_id: int,
    payload: SegmentCutoverIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*SEGMENT_WRITE_ROLES)),
) -> dict:
    return segment_controller.cutover_segment(db, experiment_id, payload.model_dump(), principal, request)
