"""导出服务：实验台账 / 分流样本 / 指标检验 / 决策清单 CSV。

每套结论都必须能对应到具体投放内容：样本、指标、决策导出均带投放段编号与内容引用；
默认只导当前生效段（decision 标注是否仍有效），保证报表里不会把新旧内容混成一次实验。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CHANNEL_LABELS,
    CORRECTION_LABELS,
    EXPERIMENT_STATUS_LABELS,
    METRIC_LABELS,
    SRM_STATUS_LABELS,
    VERDICT_LABELS,
)
from src.models.assignment import Assignment
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.models.metric_result import MetricResult
from src.models.traffic_segment import TrafficSegment
from src.models.variant import Variant
from src.utils.csv_export import to_csv


def _fmt(value: float | None, digits: int = 4) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def _segments(db: Session) -> dict[int, TrafficSegment]:
    return {row.id: row for row in db.scalars(select(TrafficSegment)).all()}


def experiments_csv(db: Session, experiment_id: int | None = None) -> bytes:
    stmt = select(Experiment)
    if experiment_id:
        stmt = stmt.where(Experiment.id == experiment_id)
    experiments = db.scalars(stmt.order_by(Experiment.id)).all()
    variants = {row.id: row for row in db.scalars(select(Variant)).all()}
    decisions = {
        row.experiment_id: row
        for row in db.scalars(select(Decision).where(Decision.is_valid.is_(True))).all()
    }
    segments = _segments(db)
    headers = [
        "实验编号", "实验名称", "主指标", "状态", "负责人", "基准转化率", "目标最小效应",
        "生效投放段", "投放内容", "SRM χ²", "df", "SRM p 值", "SRM 状态", "每变体所需样本",
        "当前功效", "当前可检测效应", "变体分流计划", "决策", "决策是否有效", "开始日期", "结束日期",
    ]
    rows = []
    for item in experiments:
        plan = " / ".join(
            f"{variant.code}:{variant.ratio:.2f}"
            for variant in sorted(variants.values(), key=lambda v: (v.experiment_id, v.sort_order))
            if variant.experiment_id == item.id
        )
        decision = decisions.get(item.id)
        active = segments.get(item.active_segment_id) if item.active_segment_id else None
        rows.append(
            [
                item.code,
                item.name,
                METRIC_LABELS.get(item.primary_metric, item.primary_metric),
                EXPERIMENT_STATUS_LABELS.get(item.status, item.status),
                item.owner,
                _fmt(item.baseline_rate),
                _fmt(item.planned_mde),
                active.segment_code if active else "",
                active.content_ref if active else "",
                _fmt(item.srm_chi2, 2),
                item.srm_df or "",
                _fmt(item.srm_p_value, 6),
                SRM_STATUS_LABELS.get(item.srm_status, item.srm_status),
                item.required_per_variant or "",
                _fmt(item.power_at_current),
                _fmt(item.mde_at_current),
                plan,
                VERDICT_LABELS.get(decision.verdict, "") if decision else "",
                "有效" if decision else "",
                item.started_on.isoformat() if item.started_on else "",
                item.ended_on.isoformat() if item.ended_on else "",
            ]
        )
    return to_csv(headers, rows)


def assignments_csv(db: Session, experiment_id: int | None = None) -> bytes:
    stmt = select(Assignment)
    if experiment_id:
        stmt = stmt.where(Assignment.experiment_id == experiment_id)
    rows_in = db.scalars(
        stmt.order_by(Assignment.experiment_id, Assignment.segment_id, Assignment.stat_date, Assignment.channel)
    ).all()
    variants = {row.id: row for row in db.scalars(select(Variant)).all()}
    experiments = {row.id: row for row in db.scalars(select(Experiment)).all()}
    segments = _segments(db)
    headers = [
        "实验编号", "投放段", "投放内容", "变体", "渠道", "指标", "日期",
        "样本数", "转化数", "转化率", "记录人",
    ]
    rows = [
        [
            experiments.get(row.experiment_id).code if experiments.get(row.experiment_id) else "",
            segments.get(row.segment_id).segment_code if row.segment_id and segments.get(row.segment_id) else "",
            segments.get(row.segment_id).content_ref if row.segment_id and segments.get(row.segment_id) else "",
            variants.get(row.variant_id).code if variants.get(row.variant_id) else "",
            CHANNEL_LABELS.get(row.channel, row.channel),
            METRIC_LABELS.get(row.metric_key, row.metric_key),
            row.stat_date.isoformat() if row.stat_date else "",
            row.samples,
            row.conversions,
            _fmt(row.conversions / row.samples if row.samples else 0.0),
            row.operator_email,
        ]
        for row in rows_in
    ]
    return to_csv(headers, rows)


def metrics_csv(db: Session, experiment_id: int | None = None) -> bytes:
    stmt = select(MetricResult)
    if experiment_id:
        stmt = stmt.where(MetricResult.experiment_id == experiment_id)
    rows_in = db.scalars(
        stmt.order_by(MetricResult.experiment_id, MetricResult.segment_id, MetricResult.variant_code, MetricResult.q_value)
    ).all()
    experiments = {row.id: row for row in db.scalars(select(Experiment)).all()}
    segments = _segments(db)
    headers = [
        "实验编号", "投放段", "投放内容", "段状态", "变体", "指标", "是否主指标", "校正方法",
        "对照样本", "对照转化", "对照转化率", "实验样本", "实验转化", "实验转化率", "绝对差", "z 值",
        "p 值", "q 值(BH)", "q 值(Bonferroni)", "CI 下限", "CI 上限", "相对提升", "lift CI 下限",
        "lift CI 上限", "显著", "结论", "所需样本", "当前功效",
    ]
    segment_status_labels = {"building": "构建中", "active": "生效中", "superseded": "已顶替", "failed": "切换失败"}
    rows = []
    for item in rows_in:
        experiment = experiments.get(item.experiment_id)
        segment = segments.get(item.segment_id) if item.segment_id else None
        rows.append(
            [
                experiment.code if experiment else "",
                segment.segment_code if segment else "",
                segment.content_ref if segment else "",
                segment_status_labels.get(segment.status, "") if segment else "",
                item.variant_code,
                item.metric_name or METRIC_LABELS.get(item.metric_key, item.metric_key),
                "是" if item.is_primary else "否",
                CORRECTION_LABELS.get(item.method, item.method),
                item.control_n,
                item.control_conversions,
                _fmt(item.control_rate),
                item.variant_n,
                item.variant_conversions,
                _fmt(item.variant_rate),
                _fmt(item.diff),
                _fmt(item.z, 3),
                _fmt(item.p_value, 6),
                _fmt(item.q_bh, 6),
                _fmt(item.q_bonferroni, 6),
                _fmt(item.ci_low),
                _fmt(item.ci_high),
                _fmt(item.lift),
                _fmt(item.lift_ci_low),
                _fmt(item.lift_ci_high),
                "是" if item.significant else "否",
                VERDICT_LABELS.get(item.verdict, item.verdict),
                item.required_n,
                _fmt(item.power_at_current),
            ]
        )
    return to_csv(headers, rows)


def decisions_csv(db: Session) -> bytes:
    decisions = db.scalars(select(Decision).order_by(Decision.id)).all()
    experiments = {row.id: row for row in db.scalars(select(Experiment)).all()}
    segments = _segments(db)
    headers = [
        "实验编号", "实验名称", "投放段", "投放内容", "结论", "是否有效", "失效原因",
        "理由", "决策人", "决策时间", "SRM p 值",
    ]
    rows = []
    for item in decisions:
        experiment = experiments.get(item.experiment_id)
        segment = segments.get(item.segment_id) if item.segment_id else None
        rows.append(
            [
                experiment.code if experiment else "",
                experiment.name if experiment else "",
                segment.segment_code if segment else "",
                segment.content_ref if segment else "",
                VERDICT_LABELS.get(item.verdict, item.verdict),
                "有效" if item.is_valid else "已失效",
                item.invalid_reason or "",
                item.rationale,
                item.decided_by,
                item.decided_at.strftime("%Y-%m-%d %H:%M") if item.decided_at else "",
                _fmt(experiment.srm_p_value, 6) if experiment else "",
            ]
        )
    return to_csv(headers, rows)
