"""分流样本服务：按 (实验, 变体, 渠道, 指标, 日期) 登记与聚合。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_LABELS, CHANNEL_ORDER, METRIC_LABELS
from src.models.assignment import Assignment
from src.models.experiment import Experiment
from src.models.variant import Variant
from src.utils.errors import AppError
from src.utils.timeutil import iso_date, iso_utc


def serialize(row: Assignment, variant: Variant | None = None) -> dict:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
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


def list_assignments(
    db: Session,
    experiment_id: int,
    *,
    variant_code: str | None = None,
    channel: str | None = None,
    metric_key: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    stmt = select(Assignment).where(Assignment.experiment_id == experiment_id)
    count_stmt = select(func.count()).select_from(Assignment).where(Assignment.experiment_id == experiment_id)
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
        "items": [serialize(row, variants.get(row.variant_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def variant_totals(db: Session, experiment: Experiment, metric_key: str | None = None) -> list[dict]:
    """按变体聚合分流样本（SRM 的输入）。"""
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
        .join(Assignment, and_(Assignment.variant_id == Variant.id, Assignment.metric_key == metric))
        .where(Variant.experiment_id == experiment.id)
        .group_by(Variant.id, Variant.code, Variant.name, Variant.ratio, Variant.is_control, Variant.sort_order)
        .order_by(Variant.sort_order, Variant.id)
    ).all()
    if not rows:
        # 没有样本时也要列出变体，便于页面提示「先录入样本」
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


def metric_keys(db: Session, experiment_id: int) -> list[str]:
    rows = db.execute(
        select(Assignment.metric_key).where(Assignment.experiment_id == experiment_id).group_by(Assignment.metric_key)
    ).all()
    return [row[0] for row in rows]


def channel_matrix(db: Session, experiment: Experiment, metric_key: str | None = None) -> dict:
    """渠道 × 变体样本矩阵（页面「各变体样本对照」表）。"""
    metric = metric_key or experiment.primary_metric
    rows = db.execute(
        select(
            Assignment.channel,
            Variant.code,
            func.coalesce(func.sum(Assignment.samples), 0),
            func.coalesce(func.sum(Assignment.conversions), 0),
        )
        .join(Variant, Variant.id == Assignment.variant_id)
        .where(Assignment.experiment_id == experiment.id, Assignment.metric_key == metric)
        .group_by(Assignment.channel, Variant.code)
    ).all()
    variants = db.scalars(
        select(Variant).where(Variant.experiment_id == experiment.id).order_by(Variant.sort_order, Variant.id)
    ).all()
    matrix = {channel: {variant.code: {"samples": 0, "conversions": 0} for variant in variants} for channel in CHANNEL_ORDER}
    for channel, code, samples, conversions in rows:
        matrix.setdefault(channel, {})[code] = {"samples": int(samples), "conversions": int(conversions)}
    return {
        "metric_key": metric,
        "metric_label": METRIC_LABELS.get(metric, metric),
        "variants": [{"code": item.code, "name": item.name, "is_control": item.is_control} for item in variants],
        "channels": [
            {"key": channel, "label": CHANNEL_LABELS.get(channel, channel), "cells": matrix.get(channel, {})}
            for channel in CHANNEL_ORDER
        ],
    }


def daily_series(db: Session, experiment: Experiment, metric_key: str | None = None) -> list[dict]:
    metric = metric_key or experiment.primary_metric
    rows = db.execute(
        select(Assignment.stat_date, func.coalesce(func.sum(Assignment.samples), 0), func.coalesce(func.sum(Assignment.conversions), 0))
        .where(Assignment.experiment_id == experiment.id, Assignment.metric_key == metric)
        .group_by(Assignment.stat_date)
        .order_by(Assignment.stat_date)
    ).all()
    return [
        {"date": iso_date(row[0]), "samples": int(row[1]), "conversions": int(row[2])} for row in rows
    ]


def create_assignment(db: Session, experiment: Experiment, payload: dict, *, operator_email: str) -> Assignment:
    variant = db.scalar(
        select(Variant).where(Variant.experiment_id == experiment.id, Variant.code == payload["variant_code"])
    )
    if variant is None:
        raise AppError("NOT_FOUND", 404, {"entity": "variant", "code": payload["variant_code"]})
    existing = db.scalar(
        select(Assignment).where(
            Assignment.experiment_id == experiment.id,
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
                "reason": "同一 (实验, 变体, 渠道, 指标, 日期) 的分流样本已存在",
                "existing_id": existing.id,
            },
        )
    row = Assignment(
        experiment_id=experiment.id,
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
    return row


def upsert_assignment(
    db: Session,
    experiment: Experiment,
    *,
    variant_id: int,
    channel: str,
    metric_key: str,
    stat_date: date,
    samples: int,
    conversions: int,
    operator_email: str,
) -> Assignment:
    """seed 专用：自然键 upsert，不覆盖人工改过的复核/决策状态。"""
    existing = db.scalar(
        select(Assignment).where(
            Assignment.experiment_id == experiment.id,
            Assignment.variant_id == variant_id,
            Assignment.channel == channel,
            Assignment.metric_key == metric_key,
            Assignment.stat_date == stat_date,
        )
    )
    if existing is None:
        existing = Assignment(
            experiment_id=experiment.id,
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
