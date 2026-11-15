"""投放段控制器：登记投放内容、查看段时间线、原子切换（cutover）。

写操作全部在单个数据库事务内完成：完整性校验失败 → 回滚并把 building 段标记 failed，
旧 active 段的完整结果继续对外，保证任何时刻都不会露出半套新结果。
"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.models.traffic_segment import TrafficSegment
from src.services import audit_service, experiment_service, metric_service, segment_service, srm_service
from src.utils.errors import AppError


def list_segments(db: Session, experiment_id: int) -> dict:
    experiment = experiment_service.get_experiment(db, experiment_id)
    segments = segment_service.list_segments(db, experiment.id)
    return {
        "experiment_id": experiment.id,
        "experiment_code": experiment.code,
        "active_segment_id": experiment.active_segment_id,
        "items": [segment_service.serialize(item) for item in segments],
        "total": len(segments),
    }


def register_content(
    db: Session, experiment_id: int, payload: dict, principal: dict, request: Request
) -> dict:
    """登记实际投放内容：同内容幂等返回，新内容立即顶替旧段（旧结论当场失效）。"""
    experiment = experiment_service.get_experiment(db, experiment_id)
    segment, created = segment_service.register_or_get(
        db,
        experiment,
        content_ref=payload["content_ref"],
        content_payload=payload.get("content_payload") or {},
        operator_email=principal["email"],
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="segment.register" if created else "segment.reuse",
        entity="traffic_segment",
        entity_id=segment.id,
        detail={
            "experiment": experiment.code,
            "segment": segment.segment_code,
            "content_ref": segment.content_ref,
            "content_hash": segment.content_hash,
            "created": created,
            "status": segment.status,
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return segment_service.serialize(segment)


def cutover_segment(
    db: Session, experiment_id: int, payload: dict, principal: dict, request: Request
) -> dict:
    """把 building 段完整计算并原子切成 active；失败保留旧版完整结果。"""
    experiment = experiment_service.get_experiment(db, experiment_id)
    target = (
        segment_service.get_segment(db, payload["segment_id"])
        if payload.get("segment_id")
        else _current_building(db, experiment)
    )
    if target.experiment_id != experiment.id:
        raise AppError("VALIDATION", 422, {"reason": "投放段不属于该实验", "segment_id": target.id})
    target_id = target.id
    target_code = target.segment_code

    try:
        segment = segment_service.get_segment(db, target_id)
        # 先在 building 段上把分流判断与全部指标补齐（不触碰 active 段的快照与结果）
        srm_service.check(db, experiment, segment=segment, operator_email=principal["email"])
        metric_service.run_checks(db, experiment, segment=segment, operator_email=principal["email"])
        segment_service.cutover(db, experiment, segment)
    except AppError as exc:
        # 整笔回滚：任何半成品 SRM/指标行都不落库，旧 active 段完整结果原样保留
        db.rollback()
        _handle_failure(db, experiment, target_id, target_code, principal, request, exc)
        raise

    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="segment.cutover",
        entity="traffic_segment",
        entity_id=target_id,
        detail={"experiment": experiment.code, "segment": target_code},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return segment_service.serialize(segment_service.get_segment(db, target_id))


def _handle_failure(db, experiment, target_id, target_code, principal, request, exc) -> None:
    """回滚后的独立事务：按错误类型决定 building 段去留，并留痕，不影响旧 active 段。

    - 完整性闸门失败（SEGMENT_INCOMPLETE/SEGMENT_FAILED）：该候选段作废 → failed；
    - 缺样本等可补数据的计算错误（NO_SAMPLES/VALIDATION）：保留 building，补数据后可重试，
      不会因为同一次变更的重试而重复建立投放段。
    """
    fatal_gate = {"SEGMENT_INCOMPLETE", "SEGMENT_FAILED"}
    try:
        segment = db.get(TrafficSegment, target_id)
        if segment is None:
            return
        action = "segment.cutover_failed"
        if exc.code in fatal_gate and segment.status == "building":
            segment_service.mark_failed(db, segment, f"完整性校验失败：{exc.code}，已保留旧版完整结果")
        else:
            # 保持 building，仅记录一次失败尝试
            action = "segment.cutover_retryable"
        audit_service.record(
            db,
            actor_email=principal["email"],
            actor_role=principal["role"],
            action=action,
            entity="traffic_segment",
            entity_id=target_id,
            detail={
                "experiment": experiment.code,
                "segment": target_code,
                "reason": segment.ready_reason,
                "error": exc.code,
            },
            ip=request.client.host if request.client else None,
        )
        db.commit()
    except Exception:  # noqa: BLE001 - 失败标记本身不能掩盖原始业务错误
        db.rollback()


def _current_building(db: Session, experiment) -> TrafficSegment:
    segments = segment_service.list_segments(db, experiment.id)
    building = [item for item in segments if item.status == "building"]
    if not building:
        raise AppError(
            "NO_BUILDING_SEGMENT",
            409,
            {"reason": "没有构建中的投放段；若上游内容已变化，请先登记新的投放内容", "experiment": experiment.code},
        )
    return building[-1]
