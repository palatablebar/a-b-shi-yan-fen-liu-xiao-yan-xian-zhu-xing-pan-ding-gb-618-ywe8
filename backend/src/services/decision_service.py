"""决策服务：一次实验一个结论，重复创建返回 409。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.constants.enums import VERDICT_LABELS
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def serialize(row: Decision, experiment: Experiment | None = None) -> dict:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "experiment_code": experiment.code if experiment else "",
        "experiment_name": experiment.name if experiment else "",
        "verdict": row.verdict,
        "verdict_label": VERDICT_LABELS.get(row.verdict, row.verdict),
        "rationale": row.rationale,
        "decided_by": row.decided_by,
        "decided_at": iso_utc(row.decided_at),
    }


def get_by_experiment(db: Session, experiment_id: int) -> Decision | None:
    return db.scalar(select(Decision).where(Decision.experiment_id == experiment_id))


def create(db: Session, experiment: Experiment, payload: dict, *, decided_by: str) -> Decision:
    existing = get_by_experiment(db, experiment.id)
    if existing is not None:
        raise AppError(
            "CONFLICT",
            409,
            {"reason": "该实验已有决策，自然键 experiment_id 唯一", "existing_id": existing.id},
        )
    row = Decision(
        experiment_id=experiment.id,
        verdict=payload["verdict"],
        rationale=payload["rationale"],
        decided_by=decided_by,
        decided_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def list_decisions(
    db: Session,
    *,
    verdict: str | None = None,
    q: str | None = None,
    limit: int = 40,
    offset: int = 0,
) -> dict:
    stmt = select(Decision)
    count_stmt = select(func.count()).select_from(Decision)
    if verdict:
        stmt = stmt.where(Decision.verdict == verdict)
        count_stmt = count_stmt.where(Decision.verdict == verdict)
    if q:
        like = f"%{q.strip()}%"
        clause = or_(Decision.rationale.ilike(like), Decision.decided_by.ilike(like))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Decision.decided_at.desc(), Decision.id.desc()).limit(limit).offset(offset)).all()
    experiments = {
        item.id: item
        for item in db.scalars(select(Experiment).where(Experiment.id.in_([row.experiment_id for row in rows]))).all()
    } if rows else {}
    return {
        "items": [serialize(row, experiments.get(row.experiment_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
