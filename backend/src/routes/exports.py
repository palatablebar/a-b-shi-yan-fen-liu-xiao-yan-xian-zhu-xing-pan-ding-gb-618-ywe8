from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EXPORT_ROLES
from src.controllers import export_controller
from src.middlewares.rbac import require_roles

router = APIRouter(prefix="/exports", tags=["exports"])

ALLOWED = {"experiments", "assignments", "metrics", "decisions"}


@router.get("/{kind}.csv")
def export_csv(
    kind: str,
    request: Request,
    experiment_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EXPORT_ROLES)),
):
    if kind not in ALLOWED:
        from src.utils.errors import AppError

        raise AppError("NOT_FOUND", 404, {"entity": "export", "kind": kind, "allowed": sorted(ALLOWED)})
    return export_controller.export_csv(db, kind, experiment_id, principal, request)
