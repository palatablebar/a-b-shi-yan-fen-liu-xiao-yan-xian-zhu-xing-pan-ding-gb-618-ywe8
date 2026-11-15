"""决策服务：结论绑定当前生效投放段，段不完整/未切换一律拒绝。

口径：
- 同一实验同时只允许一条有效决策（重复返回 409）；
- 决策必须落在 active 且样本/SRM/指标三块完整的投放段上；
- 投放内容变化、旧段被顶替时，旧决策由 segment_service 立即置为 is_valid=False；
- 历史决策保留可追溯，列表/导出标注其对应投放内容与是否仍有效。
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.constants.enums import VERDICT_LABELS
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.models.traffic_segment import TrafficSegment
from src.services import segment_service
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def serialize(row: Decision, experiment: Experiment | None = None, segment: TrafficSegment | None = None) -> dict:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "segment_id": row.segment_id,
        "segment_code": segment.segment_code if segment else "",
        "segment_seq": segment.seq if segment else None,
        "content_ref": segment.content_ref if segment else "",
        "content_summary": segment.content_summary if segment else "",
        "segment_status": segment.status if segment else "",
        "experiment_code": experiment.code if experiment else "",
        "experiment_name": experiment.name if experiment else "",
        "verdict": row.verdict,
        "verdict_label": VERDICT_LABELS.get(row.verdict, row.verdict),
        "rationale": row.rationale,
        "is_valid": row.is_valid,
        "invalid_reason": row.invalid_reason,
        "decided_by": row.decided_by,
        "decided_at": iso_utc(row.decided_at),
    }


def get_valid_by_experiment(db: Session, experiment_id: int) -> Decision | None:
    return db.scalar(
        select(Decision).where(Decision.experiment_id == experiment_id, Decision.is_valid.is_(True))
    )


def get_by_experiment(db: Session, experiment_id: int) -> Decision | None:
    """兼容旧调用：返回最新一条决策（含已失效）。"""
    return db.scalar(
        select(Decision)
        .where(Decision.experiment_id == experiment_id)
        .order_by(Decision.id.desc())
        .limit(1)
    )


def create(db: Session, experiment: Experiment, payload: dict, *, decided_by: str) -> Decision:
    # 闸门：只能基于当前生效且完整的投放段出决策
    segment = segment_service.active_segment(db, experiment.id)
    if segment is None:
        raise AppError(
            "NO_ACTIVE_SEGMENT",
            409,
            {"reason": "实验还没有生效投放段，新一段完整切换成功前不能出决策", "experiment": experiment.code},
        )
    segment_service.assert_decision_ready(db, segment)

    existing = get_valid_by_experiment(db, experiment.id)
    if existing is not None:
        raise AppError(
            "CONFLICT",
            409,
            {
                "reason": "该实验当前生效投放段已有有效决策，自然键 (experiment_id, is_valid) 唯一",
                "existing_id": existing.id,
                "segment": segment.segment_code,
            },
        )
    row = Decision(
        experiment_id=experiment.id,
        segment_id=segment.id,
        verdict=payload["verdict"],
        rationale=payload["rationale"],
        is_valid=True,
        valid_slot=experiment.id,
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
    valid_only: bool | None = None,
    limit: int = 40,
    offset: int = 0,
) -> dict:
    stmt = select(Decision)
    count_stmt = select(func.count()).select_from(Decision)
    if verdict:
        stmt = stmt.where(Decision.verdict == verdict)
        count_stmt = count_stmt.where(Decision.verdict == verdict)
    if valid_only:
        stmt = stmt.where(Decision.is_valid.is_(True))
        count_stmt = count_stmt.where(Decision.is_valid.is_(True))
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
    segments = {
        item.id: item
        for item in db.scalars(
            select(TrafficSegment).where(TrafficSegment.id.in_([row.segment_id for row in rows if row.segment_id]))
        ).all()
    } if rows else {}
    return {
        "items": [
            serialize(row, experiments.get(row.experiment_id), segments.get(row.segment_id)) for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
