"""投放段领域服务：内容绑定、幂等建段、原子切换、失效与完整性账本。

关键不变量（对应需求）：
1. 每次实际投放的内容和样本绑在一起 —— 样本/检验/指标全部带 segment_id；
2. 同一段的样本、分流判断（SRM）、全部指标、上线结论一致后才开放决策；
3. 上游投放内容变化 → 旧段立即 superseded、旧决策立即失效；
4. 新一段完整计算成功前不切换决策依据；切换失败保留旧版完整结果，不露出半套新结果；
5. 同一次变更即使重试也不重复建段 —— (experiment_id, content_hash) 唯一 + 幂等查询。
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.assignment import Assignment
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.models.metric_result import MetricResult
from src.models.srm_result import SrmResult
from src.models.traffic_segment import (
    SEGMENT_ACTIVE,
    SEGMENT_BUILDING,
    SEGMENT_FAILED,
    SEGMENT_STATUSES,
    SEGMENT_SUPERSEDED,
    TrafficSegment,
)
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow

# 完整性账本需要齐备的三块；任一块缺失都不允许 cutover / 决策
REQUIRED_BLOCKS = ("samples", "srm", "metrics")


# --------------------------------------------------------------------------- #
# 内容指纹
# --------------------------------------------------------------------------- #
def canonical_content(content_ref: str, content_payload: dict | None) -> tuple[str, str]:
    """把投放内容规范化成 (content_hash, content_summary)。

    用 sort_keys 的 JSON 做稳定序列化，字段顺序不同但内容相同视为同一次投放
    （重试/重复登记不新建段）；任意字段变化都会改变哈希。
    """
    payload = content_payload or {}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{content_ref}\n{raw}".encode("utf-8")).hexdigest()
    summary = content_ref or (raw[:180] + ("…" if len(raw) > 180 else ""))
    return digest, summary


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
def get_segment(db: Session, segment_id: int) -> TrafficSegment:
    segment = db.get(TrafficSegment, segment_id)
    if segment is None:
        raise AppError("NOT_FOUND", 404, {"entity": "traffic_segment", "id": segment_id})
    return segment


def active_segment(db: Session, experiment_id: int) -> TrafficSegment | None:
    return db.scalar(
        select(TrafficSegment).where(
            TrafficSegment.experiment_id == experiment_id,
            TrafficSegment.is_active.is_(True),
            TrafficSegment.status == SEGMENT_ACTIVE,
        )
    )


def active_segment_id(db: Session, experiment_id: int) -> int | None:
    segment = active_segment(db, experiment_id)
    return segment.id if segment else None


def list_segments(db: Session, experiment_id: int) -> list[TrafficSegment]:
    return list(
        db.scalars(
            select(TrafficSegment)
            .where(TrafficSegment.experiment_id == experiment_id)
            .order_by(TrafficSegment.seq, TrafficSegment.id)
        ).all()
    )


def find_by_content(db: Session, experiment_id: int, content_hash: str) -> TrafficSegment | None:
    """幂等键：只在仍占槽（building/active）的段里找同内容；failed/superseded 不挡重新登记。"""
    return db.scalar(
        select(TrafficSegment).where(
            TrafficSegment.experiment_id == experiment_id,
            TrafficSegment.content_hash == content_hash,
            TrafficSegment.dedup_slot.is_not(None),
        )
    )


# --------------------------------------------------------------------------- #
# 序列化
# --------------------------------------------------------------------------- #
def serialize(segment: TrafficSegment, *, decision: Decision | None = None, stale: bool | None = None) -> dict:
    return {
        "id": segment.id,
        "experiment_id": segment.experiment_id,
        "segment_code": segment.segment_code,
        "seq": segment.seq,
        "content_ref": segment.content_ref,
        "content_hash": segment.content_hash,
        "content_summary": segment.content_summary,
        "content_payload": segment.content_payload or {},
        "status": segment.status,
        "status_label": status_label(segment.status),
        "is_active": segment.is_active,
        # stale：段仍是当前生效依据，但上游已登记更新的投放内容，其结论已失效
        "stale": bool(stale) if stale is not None else False,
        "completeness": {
            "samples_ready": segment.samples_ready,
            "srm_ready": segment.srm_ready,
            "metrics_ready": segment.metrics_ready,
            "complete": segment.complete,
            "ready_reason": segment.ready_reason,
        },
        "activated_at": iso_utc(segment.activated_at),
        "superseded_at": iso_utc(segment.superseded_at),
        "created_by": segment.created_by,
        "created_at": iso_utc(segment.created_at),
        "updated_at": iso_utc(segment.updated_at),
        "decision": _serialize_decision(decision) if decision else None,
    }


def _serialize_decision(decision: Decision) -> dict:
    return {
        "id": decision.id,
        "verdict": decision.verdict,
        "is_valid": decision.is_valid,
        "invalid_reason": decision.invalid_reason,
        "decided_by": decision.decided_by,
        "decided_at": iso_utc(decision.decided_at),
    }


# --------------------------------------------------------------------------- #
# 建段 / 换段
# --------------------------------------------------------------------------- #
def _next_seq(db: Session, experiment_id: int) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(TrafficSegment.seq), 0)).where(
            TrafficSegment.experiment_id == experiment_id
        )
    )
    return int(current or 0) + 1


def register_or_get(
    db: Session,
    experiment: Experiment,
    *,
    content_ref: str,
    content_payload: dict | None,
    operator_email: str,
) -> tuple[TrafficSegment, bool]:
    """登记一次实际投放内容。

    返回 (segment, created)。内容哈希命中仍占槽（building/active）的段时直接返回（重试不重复建段）：
    - 命中 active 段：说明内容没变化，继续往当前段累计；
    - 命中 building 段：同一次变更的重试，复用该 building 段；
    - 仅命中 failed/superseded 段（已释放幂等槽位）：视为重新登记，创建新的 building 候选段。
    内容是全新的 → 建 building 段，但**不切换**当前生效段（决策依据保持旧版完整结果）；
    同时立即作废旧 active 段上的有效决策（上游内容变化，旧结论当场失效），
    并把更早的、尚未切换的 building 尝试作废，只保留最新一个候选段。
    """
    content_hash, summary = canonical_content(content_ref, content_payload)
    existing = find_by_content(db, experiment.id, content_hash)
    if existing is not None:
        return existing, False

    segment = TrafficSegment(
        experiment_id=experiment.id,
        seq=_next_seq(db, experiment.id),
        content_ref=content_ref,
        content_hash=content_hash,
        content_summary=summary,
        content_payload=content_payload or {},
        status=SEGMENT_BUILDING,
        is_active=False,
        dedup_slot=experiment.id,
        created_by=operator_email,
    )
    segment.segment_code = f"{experiment.code}-S{segment.seq:02d}"
    db.add(segment)
    db.flush()

    # 更早的未切换候选段已被本次内容变更取代，直接作废（它们从未成为决策依据）
    _obsolete_pending_segments(db, experiment.id, keep_id=segment.id)

    # 上游内容变化：旧结论立即失效；但旧 active 段保留为当前决策依据直到新段 cutover 成功
    current = active_segment(db, experiment.id)
    if current is not None:
        _invalidate_decisions(
            db,
            current.id,
            reason=f"上游投放内容变化，投放段 {current.segment_code} 的结论在新段切换前即失效",
        )
    db.flush()
    return segment, True


def _obsolete_pending_segments(db: Session, experiment_id: int, *, keep_id: int) -> None:
    pending = db.scalars(
        select(TrafficSegment).where(
            TrafficSegment.experiment_id == experiment_id,
            TrafficSegment.status == SEGMENT_BUILDING,
            TrafficSegment.id != keep_id,
        )
    ).all()
    for item in pending:
        item.status = SEGMENT_FAILED
        item.dedup_slot = None
        item.ready_reason = "上游投放内容再次变化，该候选段被更新的投放段取代"
    db.flush()


def has_newer_segment(db: Session, segment: TrafficSegment) -> bool:
    """该段之后是否已登记更新的投放内容（building/failed 均可）——是则当前段结论已过时。"""
    newer = db.scalar(
        select(TrafficSegment.id).where(
            TrafficSegment.experiment_id == segment.experiment_id,
            TrafficSegment.seq > segment.seq,
        ).limit(1)
    )
    return newer is not None


def _invalidate_decisions(db: Session, segment_id: int, *, reason: str) -> int:
    decisions = db.scalars(
        select(Decision).where(Decision.segment_id == segment_id, Decision.is_valid.is_(True))
    ).all()
    for decision in decisions:
        decision.is_valid = False
        decision.valid_slot = None
        decision.invalid_reason = reason
    db.flush()
    return len(decisions)


# --------------------------------------------------------------------------- #
# 完整性账本
# --------------------------------------------------------------------------- #
def refresh_completeness(db: Session, segment: TrafficSegment) -> TrafficSegment:
    """根据段内实际数据重算三块就绪标志，给出缺块原因。"""
    sample_sum = db.scalar(
        select(func.coalesce(func.sum(Assignment.samples), 0)).where(
            Assignment.segment_id == segment.id
        )
    ) or 0
    srm_count = db.scalar(
        select(func.coalesce(func.count(), 0)).select_from(SrmResult).where(
            SrmResult.segment_id == segment.id
        )
    ) or 0
    metric_count = db.scalar(
        select(func.coalesce(func.count(), 0)).select_from(MetricResult).where(
            MetricResult.segment_id == segment.id
        )
    ) or 0

    segment.samples_ready = sample_sum > 0
    segment.srm_ready = srm_count > 0
    segment.metrics_ready = metric_count > 0

    missing = [
        label
        for flag, label in (
            (segment.samples_ready, "分流样本"),
            (segment.srm_ready, "SRM 分流判断"),
            (segment.metrics_ready, "指标检验"),
        )
        if not flag
    ]
    segment.complete = not missing
    segment.ready_reason = "" if segment.complete else "缺少：" + "、".join(missing)
    db.flush()
    return segment


def assert_decision_ready(db: Session, segment: TrafficSegment) -> None:
    """开放决策前的闸门：段必须 active、三块完整、且没有更新的投放内容在途。"""
    refresh_completeness(db, segment)
    if segment.status != SEGMENT_ACTIVE or not segment.is_active:
        raise AppError(
            "SEGMENT_NOT_ACTIVE",
            409,
            {
                "reason": "该投放段还不是当前生效段，新一段完整切换成功前不能据此出决策",
                "segment": segment.segment_code,
                "status": segment.status,
            },
        )
    if has_newer_segment(db, segment):
        raise AppError(
            "SEGMENT_SUPERSEDED_PENDING",
            409,
            {
                "reason": "上游投放内容已变化，旧投放段结论已失效；请等新投放段完整切换后再出决策",
                "segment": segment.segment_code,
            },
        )
    if not segment.complete:
        raise AppError(
            "SEGMENT_INCOMPLETE",
            422,
            {"reason": f"投放段结果不完整，{segment.ready_reason}；齐备后才开放决策", "segment": segment.segment_code},
        )


# --------------------------------------------------------------------------- #
# 原子切换（cutover）
# --------------------------------------------------------------------------- #
def cutover(db: Session, experiment: Experiment, segment: TrafficSegment) -> TrafficSegment:
    """把一个 building 段原子切成 active。

    事务内完成：完整性复核 → 旧段顶替/旧决策失效 → 新段激活 → 实验指针切换。
    任一步抛错由外层回滚，building 段标记 failed，旧 active 段及其完整结果原样保留。
    """
    refresh_completeness(db, segment)
    if segment.status == SEGMENT_FAILED:
        raise AppError("SEGMENT_FAILED", 409, {"reason": "该投放段切换失败已作废，请基于当前内容重新登记", "segment": segment.segment_code})
    if segment.status == SEGMENT_ACTIVE and segment.is_active:
        # 幂等：已经激活过的段重复 cutover 直接返回，不重复顶替、不重复建段
        return segment
    if not segment.complete:
        segment.status = SEGMENT_FAILED
        segment.dedup_slot = None
        db.flush()
        raise AppError(
            "SEGMENT_INCOMPLETE",
            422,
            {
                "reason": f"投放段完整性校验未通过（{segment.ready_reason}），已保留旧版完整结果，不切换决策依据",
                "segment": segment.segment_code,
            },
        )

    previous = active_segment(db, experiment.id)
    if previous is not None and previous.id != segment.id:
        # 只有新段完整性通过、走到这里才顶替旧段 —— 失败时上面已抛错，旧 active 原样保留
        previous.status = SEGMENT_SUPERSEDED
        previous.is_active = False
        previous.active_slot = None
        previous.dedup_slot = None
        previous.superseded_at = utcnow()
        _invalidate_decisions(
            db,
            previous.id,
            reason=f"上游投放内容变化，投放段 {previous.segment_code} 被 {segment.segment_code} 顶替",
        )

    segment.status = SEGMENT_ACTIVE
    segment.is_active = True
    segment.active_slot = experiment.id
    segment.dedup_slot = experiment.id
    segment.activated_at = segment.activated_at or utcnow()
    experiment.active_segment_id = segment.id
    # 切换决策依据时，把新段的分流判断同步为实验级快照（页面/总览只认 active 段）
    from src.services import srm_service

    srm_service.promote_active_snapshot(db, experiment, segment)
    db.flush()
    return segment


def mark_failed(db: Session, segment: TrafficSegment | None, reason: str) -> None:
    """切换/计算失败时显式作废 building 段；旧 active 段不受影响。"""
    if segment is None or segment.status != SEGMENT_BUILDING:
        return
    segment.status = SEGMENT_FAILED
    segment.dedup_slot = None
    segment.ready_reason = reason[:300]
    db.flush()


# --------------------------------------------------------------------------- #
# 历史数据回填（baseline 段）
# --------------------------------------------------------------------------- #
def ensure_baseline_segments(db: Session) -> int:
    """为没有任何投放段的实验补一个 baseline active 段，并把存量数据挂到该段。

    用于老库升级 / seed：保证「样本-校验-指标-决策」始终能解析到一个投放段。
    幂等：实验已有段则跳过。
    """
    experiments = db.scalars(select(Experiment)).all()
    touched = 0
    for experiment in experiments:
        if list_segments(db, experiment.id):
            continue
        payload = {"source": "baseline", "note": "系统初始化投放段，承接升级前的存量样本与结论"}
        content_hash, summary = canonical_content("baseline://initial", payload)
        segment = TrafficSegment(
            experiment_id=experiment.id,
            seq=1,
            segment_code=f"{experiment.code}-S01",
            content_ref="baseline://initial",
            content_hash=content_hash,
            content_summary=summary,
            content_payload=payload,
            status=SEGMENT_ACTIVE,
            is_active=True,
            active_slot=experiment.id,
            dedup_slot=experiment.id,
            activated_at=utcnow(),
            created_by="system",
        )
        db.add(segment)
        db.flush()
        experiment.active_segment_id = segment.id

        # 存量样本 / 指标挂到 baseline 段
        db.execute(
            Assignment.__table__.update()
            .where(Assignment.experiment_id == experiment.id, Assignment.segment_id.is_(None))
            .values(segment_id=segment.id)
        )
        db.execute(
            MetricResult.__table__.update()
            .where(MetricResult.experiment_id == experiment.id, MetricResult.segment_id.is_(None))
            .values(segment_id=segment.id)
        )
        # 存量 SRM 快照固化成段结果
        if experiment.srm_checked_at is not None:
            db.add(
                SrmResult(
                    segment_id=segment.id,
                    experiment_id=experiment.id,
                    chi2=experiment.srm_chi2,
                    df=experiment.srm_df,
                    p_value=experiment.srm_p_value,
                    status=experiment.srm_status,
                    alarm=experiment.has_srm_alarm,
                    required_per_variant=experiment.required_per_variant,
                    power_at_current=experiment.power_at_current,
                    mde_at_current=experiment.mde_at_current,
                    total_samples=int((experiment.srm_payload or {}).get("total") or 0),
                    payload=experiment.srm_payload or {},
                    checked_by="system",
                    checked_at=experiment.srm_checked_at,
                )
            )
        # 存量决策绑定 baseline 段（保持有效，并占住唯一槽位）
        db.execute(
            Decision.__table__.update()
            .where(Decision.experiment_id == experiment.id, Decision.segment_id.is_(None))
            .values(segment_id=segment.id, is_valid=True, valid_slot=experiment.id)
        )
        refresh_completeness(db, segment)
        touched += 1
    db.flush()
    return touched


def status_label(status: str) -> str:
    return {
        SEGMENT_BUILDING: "构建中",
        SEGMENT_ACTIVE: "生效中",
        SEGMENT_SUPERSEDED: "已顶替",
        SEGMENT_FAILED: "切换失败",
    }.get(status, status)


__all__ = [
    "SEGMENT_STATUSES",
    "canonical_content",
    "get_segment",
    "active_segment",
    "active_segment_id",
    "list_segments",
    "find_by_content",
    "serialize",
    "register_or_get",
    "refresh_completeness",
    "assert_decision_ready",
    "cutover",
    "mark_failed",
    "ensure_baseline_segments",
    "status_label",
]
