"""算法 A 的落库层：从指定投放段的 assignments 聚合 → 跑 SRM/功效 → 段结果 + 实验快照。

SRM 判断按投放段固化到 srm_results；只有 active 段的结果才回写 experiments 快照
（总览/列表沿用 experiments 字段，保证页面看到的永远是当前生效段的分流判断）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.experiment import Experiment
from src.models.srm_result import SrmResult
from src.models.traffic_segment import TrafficSegment
from src.services import assignment_service, segment_service
from src.services.algorithms import srm as srm_algorithm
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def build_variants(db: Session, experiment: Experiment, segment: TrafficSegment) -> list[dict]:
    totals = assignment_service.variant_totals(db, experiment, segment=segment)
    return [
        {
            "code": row["code"],
            "name": row["name"],
            "ratio": row["ratio"],
            "observed": row["samples"],
            "is_control": row["is_control"],
            "conversions": row["conversions"],
        }
        for row in totals
    ]


def _upsert_srm_result(
    db: Session, experiment: Experiment, segment: TrafficSegment, result: dict, *, operator: str
) -> SrmResult:
    row = db.scalar(select(SrmResult).where(SrmResult.segment_id == segment.id))
    if row is None:
        row = SrmResult(segment_id=segment.id, experiment_id=experiment.id)
        db.add(row)
    row.chi2 = result["chi2"]
    row.df = result["df"]
    row.p_value = result["p_value"]
    row.status = result["status"]
    row.alarm = result["alarm"]
    row.required_per_variant = result["required_per_variant"]
    row.power_at_current = result["power_at_current"]
    row.mde_at_current = result["mde_at_current"]
    row.total_samples = int(result.get("total") or 0)
    row.payload = result
    row.checked_by = operator
    row.checked_at = utcnow()
    db.flush()
    return row


def check(
    db: Session,
    experiment: Experiment,
    *,
    alpha: float | None = None,
    power: float | None = None,
    alarm_p: float | None = None,
    segment: TrafficSegment | None = None,
    operator_email: str = "system",
) -> dict:
    segment = segment or segment_service.active_segment(db, experiment.id)
    if segment is None:
        raise AppError(
            "NO_ACTIVE_SEGMENT",
            409,
            {"reason": "实验还没有生效投放段，先登记投放内容并完成切换", "experiment": experiment.code},
        )
    variants = build_variants(db, experiment, segment)
    if sum(item["observed"] for item in variants) <= 0:
        raise AppError(
            "NO_SAMPLES",
            422,
            {
                "reason": f"投放段 {segment.segment_code} 还没有分流样本，先按变体/渠道/日期录入样本再校验",
                "experiment": experiment.code,
                "segment": segment.segment_code,
            },
        )
    try:
        result = srm_algorithm.run_srm(
            variants,
            baseline_rate=experiment.baseline_rate,
            planned_mde=experiment.planned_mde,
            alpha=alpha if alpha is not None else experiment.alpha,
            power=power if power is not None else experiment.power_target,
            alarm_p=alarm_p if alarm_p is not None else 0.001,
        )
    except ValueError as exc:
        raise AppError("VALIDATION", 422, {"reason": str(exc)}) from exc

    _upsert_srm_result(db, experiment, segment, result, operator=operator_email)
    segment_service.refresh_completeness(db, segment)

    # 仅当该段是当前生效段时，才回写实验快照 —— building 段的校验不污染旧版完整结果
    if segment.is_active and segment.status == "active":
        _apply_snapshot(experiment, result)
    db.flush()
    return snapshot(experiment, db=db, segment=segment, result=result)


def _apply_snapshot(experiment: Experiment, result: dict) -> None:
    """把一份 SRM 结果提升为实验级快照（总览/列表的唯一分流判断来源）。"""
    experiment.srm_chi2 = result["chi2"]
    experiment.srm_df = result["df"]
    experiment.srm_p_value = result["p_value"]
    experiment.srm_status = result["status"]
    experiment.has_srm_alarm = result["alarm"]
    experiment.srm_checked_at = utcnow()
    experiment.required_per_variant = result["required_per_variant"]
    experiment.power_at_current = result["power_at_current"]
    experiment.mde_at_current = result["mde_at_current"]
    experiment.srm_payload = result


def promote_active_snapshot(db: Session, experiment: Experiment, segment: TrafficSegment) -> None:
    """cutover 时把新 active 段的 SRM 结果提升为实验快照，保证快照与生效段一致。"""
    row = db.scalar(select(SrmResult).where(SrmResult.segment_id == segment.id))
    if row is not None:
        _apply_snapshot(experiment, row.payload or {})
    db.flush()


def snapshot(
    experiment: Experiment,
    *,
    db: Session | None = None,
    segment: TrafficSegment | None = None,
    result: dict | None = None,
) -> dict:
    # 显式指定段时优先用该段固化的 SRM 结果（building/superseded 段也能回看自己的分流判断）
    payload = result
    if payload is None and segment is not None and db is not None:
        stored = db.scalar(select(SrmResult).where(SrmResult.segment_id == segment.id))
        if stored is not None:
            payload = stored.payload
    if payload is None:
        payload = experiment.srm_payload or {}
    return {
        "experiment_id": experiment.id,
        "segment_id": segment.id if segment else experiment.active_segment_id,
        "segment_code": segment.segment_code if segment else None,
        "segment_status": segment.status if segment else None,
        "status": payload.get("status", experiment.srm_status),
        "alarm": payload.get("alarm", experiment.has_srm_alarm),
        "chi2": payload.get("chi2", experiment.srm_chi2),
        "df": payload.get("df", experiment.srm_df),
        "p_value": payload.get("p_value", experiment.srm_p_value),
        "checked_at": iso_utc(experiment.srm_checked_at),
        "required_per_variant": payload.get("required_per_variant", experiment.required_per_variant),
        "power_at_current": payload.get("power_at_current", experiment.power_at_current),
        "mde_at_current": payload.get("mde_at_current", experiment.mde_at_current),
        "baseline_rate": experiment.baseline_rate,
        "planned_mde": experiment.planned_mde,
        "payload": payload,
        "cells": payload.get("cells", []),
        "gap_total": payload.get("gap_total"),
        "note": payload.get("note", ""),
    }
