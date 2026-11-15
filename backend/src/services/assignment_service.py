"""分流样本服务：按 (投放段, 变体, 渠道, 指标, 日期) 登记与聚合。

所有读聚合都强制带 segment_id —— 不同投放段的样本绝不混算，
页面默认只看当前 active 段；building 段在切换前独立累计、不影响旧结论。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_LABELS, CHANNEL_ORDER, METRIC_LABELS
from src.models.assignment import Assignment
from src.models.experiment import Experiment
from src.models.traffic_segment import TrafficSegment
from src.models.variant import Variant
from src.services import segment_service
from src.utils.errors import AppError
from src.utils.timeutil import iso_date, iso_utc


def serialize(row: Assignment, variant: Variant | None = None) -> dict:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "segment_id": row.segment_id,
        "variant_id": row.variant_id,
        "variant_code": variant.code if variant else "",
        "variant_name": variant.name if variant else "",
        "channel": row.channel,
        "channel_label": CHANNEL_LABELS.get(row.channel, row.channel),
        "metric_key": row.metric_key,
        "metric_label": METRIC_LABELS.get(row.metric_key, row.metric_key),
        "stat_date": iso_date(row.stat_date),
        "samples": row.samples,
        "conversions": row.conversions,
        "rate": round(row.conversions / row.samples, 6) if row.samples else 0.0,
        "operator_email": row.operator_email,
        "updated_at": iso_utc(row.updated_at),
    }


def resolve_segment(db: Session, experiment: Experiment, segment_id: int | None) -> TrafficSegment:
    """决定本次写操作落在哪一段：显式指定优先，否则取当前 active 段。

    只接受 building/active 段；已顶替/失败的段是封闭历史，不得再写入样本。
    """
    if segment_id is not None:
        segment = segment_service.get_segment(db, segment_id)
        if segment.experiment_id != experiment.id:
            raise AppError("VALIDATION", 422, {"reason": "投放段不属于该实验", "segment_id": segment_id})
        if segment.status not in ("building", "active"):
            raise AppError(
                "SEGMENT_CLOSED",
                409,
                {"reason": f"投放段 {segment.segment_code} 已{segment.status}，不能再写入样本", "segment": segment.segment_code},
            )
        return segment
    segment = segment_service.active_segment(db, experiment.id)
    if segment is None:
        raise AppError(
            "NO_ACTIVE_SEGMENT",
            409,
            {"reason": "实验还没有生效投放段，请先登记实际投放内容并完成投放段切换", "experiment": experiment.code},
        )
    return segment


def resolve_segment_optional(db: Session, experiment: Experiment, segment_id: int | None) -> TrafficSegment | None:
    """读路径用：没有任何投放段时返回 None，由上层给空表而不是报错。"""
    if segment_id is not None:
        return segment_service.get_segment(db, segment_id)
    return segment_service.active_segment(db, experiment.id)


def list_assignments(
    db: Session,
    experiment_id: int,
    *,
    segment_id: int | None = None,
    variant_code: str | None = None,
    channel: str | None = None,
    metric_key: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    experiment = db.get(Experiment, experiment_id)
    segment = resolve_segment_optional(db, experiment, segment_id)
    if segment is None:
        return {"segment": None, "items": [], "total": 0, "limit": limit, "offset": offset}
    stmt = select(Assignment).where(
        Assignment.experiment_id == experiment_id, Assignment.segment_id == segment.id
    )
    count_stmt = (
        select(func.count())
        .select_from(Assignment)
        .where(Assignment.experiment_id == experiment_id, Assignment.segment_id == segment.id)
    )
    if variant_code:
        variant = db.scalar(select(Variant).where(Variant.experiment_id == experiment_id, Variant.code == variant_code))
        variant_id = variant.id if variant else -1
        stmt = stmt.where(Assignment.variant_id == variant_id)
        count_stmt = count_stmt.where(Assignment.variant_id == variant_id)
    if channel:
        stmt = stmt.where(Assignment.channel == channel)
        count_stmt = count_stmt.where(Assignment.channel == channel)
    if metric_key:
        stmt = stmt.where(Assignment.metric_key == metric_key)
        count_stmt = count_stmt.where(Assignment.metric_key == metric_key)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Assignment.stat_date.desc(), Assignment.channel, Assignment.metric_key)
        .limit(limit)
        .offset(offset)
    ).all()
    variants = {item.id: item for item in db.scalars(select(Variant).where(Variant.experiment_id == experiment_id)).all()}
    return {
        "segment": segment_service.serialize(segment),
        "items": [serialize(row, variants.get(row.variant_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def variant_totals(
    db: Session, experiment: Experiment, metric_key: str | None = None, segment: TrafficSegment | None = None
) -> list[dict]:
    """按变体聚合指定投放段的分流样本（SRM 的输入）。"""
    if segment is None:
        segment = resolve_segment_optional(db, experiment, None)
    if segment is None:
        variants = db.scalars(
            select(Variant).where(Variant.experiment_id == experiment.id).order_by(Variant.sort_order, Variant.id)
        ).all()
        return [
            {"variant_id": item.id, "code": item.code, "name": item.name, "ratio": item.ratio,
             "is_control": item.is_control, "samples": 0, "conversions": 0, "rate": 0.0}
            for item in variants
        ]
    metric = metric_key or experiment.primary_metric
    rows = db.execute(
        select(
            Variant.id,
            Variant.code,
            Variant.name,
            Variant.ratio,
            Variant.is_control,
            Variant.sort_order,
            func.coalesce(func.sum(Assignment.samples), 0),
            func.coalesce(func.sum(Assignment.conversions), 0),
        )
        .join(
            Assignment,
            and_(
                Assignment.variant_id == Variant.id,
                Assignment.metric_key == metric,
                Assignment.segment_id == segment.id,
            ),
        )
        .where(Variant.experiment_id == experiment.id)
        .group_by(Variant.id, Variant.code, Variant.name, Variant.ratio, Variant.is_control, Variant.sort_order)
        .order_by(Variant.sort_order, Variant.id)
    ).all()
    if not rows:
        variants = db.scalars(
            select(Variant).where(Variant.experiment_id == experiment.id).order_by(Variant.sort_order, Variant.id)
        ).all()
        return [
            {
                "variant_id": item.id,
                "code": item.code,
                "name": item.name,
                "ratio": item.ratio,
                "is_control": item.is_control,
                "samples": 0,
                "conversions": 0,
                "rate": 0.0,
            }
            for item in variants
        ]
    total = sum(int(row[6]) for row in rows) or 1
    return [
        {
            "variant_id": row[0],
            "code": row[1],
            "name": row[2],
            "ratio": row[3],
            "is_control": row[4],
            "samples": int(row[6]),
            "conversions": int(row[7]),
            "rate": round(int(row[7]) / int(row[6]), 6) if row[6] else 0.0,
            "share_pct": round(int(row[6]) / total * 100, 4),
        }
        for row in rows
    ]


def metric_keys(db: Session, experiment_id: int, segment_id: int | None = None) -> list[str]:
    stmt = (
        select(Assignment.metric_key)
        .where(Assignment.experiment_id == experiment_id)
        .group_by(Assignment.metric_key)
    )
    if segment_id is not None:
        stmt = stmt.where(Assignment.segment_id == segment_id)
    rows = db.execute(stmt).all()
    return [row[0] for row in rows]


def channel_matrix(
    db: Session, experiment: Experiment, metric_key: str | None = None, segment: TrafficSegment | None = None
) -> dict:
    """渠道 × 变体样本矩阵（页面「各变体样本对照」表），限定单段。"""
    if segment is None:
        segment = resolve_segment_optional(db, experiment, None)
    variants = db.scalars(
        select(Variant).where(Variant.experiment_id == experiment.id).order_by(Variant.sort_order, Variant.id)
    ).all()
    if segment is None:
        matrix = {channel: {variant.code: {"samples": 0, "conversions": 0} for variant in variants} for channel in CHANNEL_ORDER}
        return {
            "segment_id": None,
            "metric_key": metric_key or experiment.primary_metric,
            "metric_label": METRIC_LABELS.get(metric_key or experiment.primary_metric, metric_key or ""),
            "variants": [{"code": item.code, "name": item.name, "is_control": item.is_control} for item in variants],
            "channels": [
                {"key": channel, "label": CHANNEL_LABELS.get(channel, channel), "cells": matrix.get(channel, {})}
                for channel in CHANNEL_ORDER
            ],
        }
    metric = metric_key or experiment.primary_metric
    rows = db.execute(
        select(
            Assignment.channel,
            Variant.code,
            func.coalesce(func.sum(Assignment.samples), 0),
            func.coalesce(func.sum(Assignment.conversions), 0),
        )
        .join(Variant, Variant.id == Assignment.variant_id)
        .where(
            Assignment.experiment_id == experiment.id,
            Assignment.metric_key == metric,
            Assignment.segment_id == segment.id,
        )
        .group_by(Assignment.channel, Variant.code)
    ).all()
    variants = db.scalars(
        select(Variant).where(Variant.experiment_id == experiment.id).order_by(Variant.sort_order, Variant.id)
    ).all()
    matrix = {channel: {variant.code: {"samples": 0, "conversions": 0} for variant in variants} for channel in CHANNEL_ORDER}
    for channel, code, samples, conversions in rows:
        matrix.setdefault(channel, {})[code] = {"samples": int(samples), "conversions": int(conversions)}
    return {
        "segment_id": segment.id,
        "metric_key": metric,
        "metric_label": METRIC_LABELS.get(metric, metric),
        "variants": [{"code": item.code, "name": item.name, "is_control": item.is_control} for item in variants],
        "channels": [
            {"key": channel, "label": CHANNEL_LABELS.get(channel, channel), "cells": matrix.get(channel, {})}
            for channel in CHANNEL_ORDER
        ],
    }


def daily_series(
    db: Session, experiment: Experiment, metric_key: str | None = None, segment: TrafficSegment | None = None
) -> list[dict]:
    if segment is None:
        segment = resolve_segment_optional(db, experiment, None)
    if segment is None:
        return []
    metric = metric_key or experiment.primary_metric
    rows = db.execute(
        select(Assignment.stat_date, func.coalesce(func.sum(Assignment.samples), 0), func.coalesce(func.sum(Assignment.conversions), 0))
        .where(
            Assignment.experiment_id == experiment.id,
            Assignment.metric_key == metric,
            Assignment.segment_id == segment.id,
        )
        .group_by(Assignment.stat_date)
        .order_by(Assignment.stat_date)
    ).all()
    return [
        {"date": iso_date(row[0]), "samples": int(row[1]), "conversions": int(row[2])} for row in rows
    ]


def create_assignment(
    db: Session,
    experiment: Experiment,
    payload: dict,
    *,
    operator_email: str,
    segment_id: int | None = None,
) -> Assignment:
    segment = resolve_segment(db, experiment, segment_id)
    variant = db.scalar(
        select(Variant).where(Variant.experiment_id == experiment.id, Variant.code == payload["variant_code"])
    )
    if variant is None:
        raise AppError("NOT_FOUND", 404, {"entity": "variant", "code": payload["variant_code"]})
    existing = db.scalar(
        select(Assignment).where(
            Assignment.segment_id == segment.id,
            Assignment.variant_id == variant.id,
            Assignment.channel == payload["channel"],
            Assignment.metric_key == payload["metric_key"],
            Assignment.stat_date == payload["stat_date"],
        )
    )
    if existing is not None:
        raise AppError(
            "CONFLICT",
            409,
            {
                "reason": "同一 (投放段, 变体, 渠道, 指标, 日期) 的分流样本已存在",
                "existing_id": existing.id,
                "segment": segment.segment_code,
            },
        )
    row = Assignment(
        experiment_id=experiment.id,
        segment_id=segment.id,
        variant_id=variant.id,
        channel=payload["channel"],
        metric_key=payload["metric_key"],
        stat_date=payload["stat_date"],
        samples=int(payload["samples"]),
        conversions=int(payload["conversions"]),
        operator_email=operator_email,
    )
    db.add(row)
    db.flush()
    segment_service.refresh_completeness(db, segment)
    return row


def upsert_assignment(
    db: Session,
    experiment: Experiment,
    *,
    segment: TrafficSegment,
    variant_id: int,
    channel: str,
    metric_key: str,
    stat_date: date,
    samples: int,
    conversions: int,
    operator_email: str,
) -> Assignment:
    """seed 专用：段内自然键 upsert，不覆盖人工改过的复核/决策状态。"""
    existing = db.scalar(
        select(Assignment).where(
            Assignment.segment_id == segment.id,
            Assignment.variant_id == variant_id,
            Assignment.channel == channel,
            Assignment.metric_key == metric_key,
            Assignment.stat_date == stat_date,
        )
    )
    if existing is None:
        existing = Assignment(
            experiment_id=experiment.id,
            segment_id=segment.id,
            variant_id=variant_id,
            channel=channel,
            metric_key=metric_key,
            stat_date=stat_date,
            samples=samples,
            conversions=conversions,
            operator_email=operator_email,
        )
        db.add(existing)
        db.flush()
        return existing
    existing.samples = samples
    existing.conversions = conversions
    db.flush()
    return existing
