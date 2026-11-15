"""导出控制器：CSV 响应 + 审计（viewer 在路由层被 403 拦住）。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers

KINDS = {
    "experiments": ("export.experiments", "experiments.csv", export_service.experiments_csv),
    "assignments": ("export.assignments", "assignments.csv", export_service.assignments_csv),
    "metrics": ("export.metrics", "metrics.csv", export_service.metrics_csv),
    "decisions": ("export.decisions", "decisions.csv", export_service.decisions_csv),
}


def export_csv(db: Session, kind: str, experiment_id: int | None, principal: dict, request: Request) -> Response:
    action, filename, builder = KINDS[kind]
    if kind == "decisions":
        content = builder(db)
    else:
        content = builder(db, experiment_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action=action,
        entity="export",
        entity_id=experiment_id,
        detail={"bytes": len(content), "rows_kind": kind},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(content=content, media_type="text/csv; charset=utf-8", headers=csv_response_headers(filename))
