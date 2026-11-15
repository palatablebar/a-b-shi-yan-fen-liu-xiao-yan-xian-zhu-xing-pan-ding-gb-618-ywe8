"""算法 B 的落库层：从 assignments 生成对照/实验组汇总 → 双比例检验 + 多重校正 → 写结果。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.constants.enums import CORRECTION_LABELS, METRIC_LABELS, VERDICT_LABELS
from src.models.assignment import Assignment
from src.models.experiment import Experiment
from src.models.metric_result import MetricResult
from src.models.variant import Variant
from src.services import variant_service
from src.services.algorithms import metric_test as metric_algorithm
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def serialize(row: MetricResult) -> dict:
    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "variant_code": row.variant_code,
        "variant_name": row.variant_name,
        "metric_key": row.metric_key,
        "metric_name": row.metric_name,
        "is_primary": row.is_primary,
        "method": row.method,
        "method_label": CORRECTION_LABELS.get(row.method, row.method),
        "control_n": row.control_n,
        "control_conversions": row.control_conversions,
        "variant_n": row.variant_n,
        "variant_conversions": row.variant_conversions,
        "control_rate": row.control_rate,
        "variant_rate": row.variant_rate,
        "diff": row.diff,
        "z": row.z,
        "p_value": row.p_value,
        "q_value": row.q_value,
        "q_bh": row.q_bh,
        "q_bonferroni": row.q_bonferroni,
        "ci_low": row.ci_low,
        "ci_high": row.ci_high,
        "lift": row.lift,
        "lift_ci_low": row.lift_ci_low,
        "lift_ci_high": row.lift_ci_high,
        "significant": row.significant,
        "verdict": row.verdict,
        "verdict_label": VERDICT_LABELS.get(row.verdict, row.verdict),
        "required_n": row.required_n,
        "power_at_current": row.power_at_current,
        "alpha": row.alpha,
        "computed_at": iso_utc(row.computed_at),
        "computed_by": row.computed_by,
    }


def _totals(db: Session, experiment_id: int, variant_id: int, metric_key: str) -> tuple[int, int]:
    row = db.execute(
        select(func.coalesce(func.sum(Assignment.samples), 0), func.coalesce(func.sum(Assignment.conversions), 0))
        .where(
            Assignment.experiment_id == experiment_id,
            Assignment.variant_id == variant_id,
            Assignment.metric_key == metric_key,
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


def run_checks(
    db: Session,
    experiment: Experiment,
    *,
    method: str = "bh",
    alpha: float | None = None,
    variant_code: str | None = None,
    operator_email: str = "system",
) -> dict:
    control = variant_service.control_variant(db, experiment.id)
    treatments = [
        item
        for item in variant_service.list_variants(db, experiment.id)
        if not item.is_control and (variant_code is None or item.code == variant_code)
    ]
    if not treatments:
        raise AppError("NOT_FOUND", 404, {"entity": "variant", "code": variant_code})

    metric_keys = [
        row[0]
        for row in db.execute(
            select(Assignment.metric_key)
            .where(Assignment.experiment_id == experiment.id)
            .group_by(Assignment.metric_key)
            .order_by(Assignment.metric_key)
        ).all()
    ]
    if not metric_keys:
        raise AppError("NO_SAMPLES", 422, {"reason": "该实验还没有分流样本，先录入样本再跑指标检验"})

    results: list[dict] = []
    for treatment in treatments:
        metrics = []
        for metric_key in metric_keys:
            n2, c2 = _totals(db, experiment.id, control.id, metric_key)
            n1, c1 = _totals(db, experiment.id, treatment.id, metric_key)
            if n1 <= 0 or n2 <= 0:
                continue
            metrics.append(
                {
                    "metric_key": metric_key,
                    "metric_name": METRIC_LABELS.get(metric_key, metric_key),
                    "is_primary": metric_key == experiment.primary_metric,
                    "control": {"n": n2, "conversions": c2},
                    "variant": {"code": treatment.code, "name": treatment.name, "n": n1, "conversions": c1},
                }
            )
        if not metrics:
            raise AppError("NO_SAMPLES", 422, {"reason": f"变体 {treatment.code} 没有可用的分流样本"})
        try:
            outcome = metric_algorithm.run_metric_tests(
                metrics,
                method=method,
                alpha=alpha if alpha is not None else experiment.alpha,
            )
        except ValueError as exc:
            raise AppError("VALIDATION", 422, {"reason": str(exc)}) from exc

        for item in outcome["items"]:
            row = db.scalar(
                select(MetricResult).where(
                    MetricResult.experiment_id == experiment.id,
                    MetricResult.variant_code == treatment.code,
                    MetricResult.metric_key == item["metric_key"],
                )
            )
            if row is None:
                row = MetricResult(
                    experiment_id=experiment.id,
                    variant_id=treatment.id,
                    variant_code=treatment.code,
                    variant_name=treatment.name,
                    metric_key=item["metric_key"],
                    metric_name=item["metric_name"],
                )
                db.add(row)
            row.variant_id = treatment.id
            row.variant_name = treatment.name
            row.metric_name = item["metric_name"]
            row.is_primary = item["is_primary"]
            row.method = method
            row.control_n = item["control_n"]
            row.control_conversions = item["control_conversions"]
            row.variant_n = item["variant_n"]
            row.variant_conversions = item["variant_conversions"]
            row.control_rate = item["control_rate"]
            row.variant_rate = item["variant_rate"]
            row.diff = item["diff"]
            row.z = item["z"]
            row.p_value = item["p_value"]
            row.q_value = item["q_value"]
            row.q_bh = item["q_bh"]
            row.q_bonferroni = item["q_bonferroni"]
            row.ci_low = item["ci_low"]
            row.ci_high = item["ci_high"]
            row.lift = item["lift"]
            row.lift_ci_low = item["lift_ci_low"]
            row.lift_ci_high = item["lift_ci_high"]
            row.significant = item["significant"]
            row.verdict = item["verdict"]
            row.required_n = item["required_n"]
            row.power_at_current = item["power_at_current"]
            row.alpha = item["alpha"]
            row.payload = item
            row.computed_at = utcnow()
            row.computed_by = operator_email
            db.flush()
        results.append(
            {
                "variant_code": treatment.code,
                "variant_name": treatment.name,
                "method": method,
                "metrics_count": outcome["metrics_count"],
                "significant_count": outcome["significant_count"],
                "primary": outcome["primary"],
                "items": outcome["items"],
                "note": outcome["note"],
            }
        )
    db.flush()
    return {
        "experiment_id": experiment.id,
        "experiment_code": experiment.code,
        "method": method,
        "method_label": CORRECTION_LABELS.get(method, method),
        "results": results,
        "total": sum(len(item["items"]) for item in results),
    }


def list_metrics(
    db: Session,
    *,
    experiment_id: int | None = None,
    variant_code: str | None = None,
    significant: bool | None = None,
    q: str | None = None,
    limit: int = 40,
    offset: int = 0,
) -> dict:
    stmt = select(MetricResult)
    count_stmt = select(func.count()).select_from(MetricResult)
    if experiment_id:
        stmt = stmt.where(MetricResult.experiment_id == experiment_id)
        count_stmt = count_stmt.where(MetricResult.experiment_id == experiment_id)
    if variant_code:
        stmt = stmt.where(MetricResult.variant_code == variant_code)
        count_stmt = count_stmt.where(MetricResult.variant_code == variant_code)
    if significant is not None:
        stmt = stmt.where(MetricResult.significant.is_(significant))
        count_stmt = count_stmt.where(MetricResult.significant.is_(significant))
    if q:
        like = f"%{q.strip()}%"
        clause = or_(MetricResult.metric_name.ilike(like), MetricResult.variant_code.ilike(like))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(MetricResult.experiment_id, MetricResult.variant_code, MetricResult.q_value, MetricResult.metric_key)
        .limit(limit)
        .offset(offset)
    ).all()
    experiments = {
        item.id: item
        for item in db.scalars(select(Experiment).where(Experiment.id.in_([row.experiment_id for row in rows]))).all()
    } if rows else {}
    items = []
    for row in rows:
        payload = serialize(row)
        experiment = experiments.get(row.experiment_id)
        payload["experiment_code"] = experiment.code if experiment else ""
        payload["experiment_name"] = experiment.name if experiment else ""
        items.append(payload)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def significant_rows(db: Session, limit: int = 5) -> list[dict]:
    rows = db.scalars(
        select(MetricResult)
        .where(MetricResult.significant.is_(True))
        .order_by(MetricResult.q_value, MetricResult.lift.desc())
        .limit(limit)
    ).all()
    experiment_codes = {
        item.id: (item.code, item.name)
        for item in db.scalars(select(Experiment).where(Experiment.id.in_([row.experiment_id for row in rows]))).all()
    } if rows else {}
    return [
        {
            **serialize(row),
            "experiment_code": experiment_codes.get(row.experiment_id, ("", ""))[0],
            "experiment_name": experiment_codes.get(row.experiment_id, ("", ""))[1],
        }
        for row in rows
    ]
