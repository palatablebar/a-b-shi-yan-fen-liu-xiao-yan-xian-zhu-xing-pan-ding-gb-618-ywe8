"""幂等 seed：3 账号 / 6 实验 / 13 变体 / 1,092 行分流样本 / 指标检验 / 4 条决策。

自然键 upsert：
  users.email
  experiments.code
  variants(experiment_id, code)
  assignments(experiment_id, variant_id, channel, metric_key, stat_date)
  metric_results(experiment_id, variant_code, metric_key)
  decisions(experiment_id)
重复执行不新增、不覆盖人工改过的决策/状态；SEED_SUMMARY 两次逐字一致。

口径映射（模板 SEED_SUMMARY 键名固定，语义按本项目落点）：
  sources  = 实验数
  runs     = 分流样本行数（assignments）
  findings = 指标检验结果数（metric_results）
  pending  = 还没有决策的实验数
"""
from __future__ import annotations

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.assignment import Assignment
from src.models.audit import AuditLog
from src.models.decision import Decision
from src.models.experiment import Experiment
from src.models.metric_result import MetricResult
from src.models.traffic_segment import TrafficSegment
from src.models.user import User
from src.models.variant import Variant
from src.services import (
    assignment_service,
    decision_service,
    experiment_service,
    metric_service,
    segment_service,
    srm_service,
)
from src.utils.security import hash_password

from scripts.demo_config import (
    DECISIONS,
    DEMO_PASSWORD,
    DEMO_USERS,
    EXPERIMENTS,
    ORG,
    assignment_cells,
)

SEED_OPERATOR = "seed@abcheck.io"


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_experiments(db) -> int:
    for spec in EXPERIMENTS:
        experiment = db.scalar(select(Experiment).where(Experiment.code == spec["code"]))
        if experiment is None:
            experiment = experiment_service.create_experiment(
                db,
                {
                    "code": spec["code"],
                    "name": spec["name"],
                    "hypothesis": spec["hypothesis"],
                    "owner": ORG,
                    "primary_metric": spec["primary_metric"],
                    "status": spec["status"],
                    "baseline_rate": spec["baseline_rate"],
                    "planned_mde": spec["planned_mde"],
                    "alpha": 0.05,
                    "power_target": 0.8,
                    "traffic_note": spec["traffic_note"],
                    "started_on": spec["started_on"],
                    "ended_on": None,
                    "variants": spec["variants"],
                },
                owner_default=ORG,
            )
            experiment.seed_key = f"seed-exp-{spec['code']}"
        else:
            # 只更新元信息，不动状态与 SRM 快照（人工改过就保留）
            experiment.hypothesis = spec["hypothesis"]
            experiment.baseline_rate = spec["baseline_rate"]
            experiment.planned_mde = spec["planned_mde"]
            experiment.traffic_note = spec["traffic_note"]
        db.flush()
    return db.scalar(select(func.count()).select_from(Experiment)) or 0


def ensure_variants(db) -> dict[str, dict[str, Variant]]:
    mapping: dict[str, dict[str, Variant]] = {}
    for spec in EXPERIMENTS:
        experiment = db.scalar(select(Experiment).where(Experiment.code == spec["code"]))
        if experiment is None:
            continue
        existing = {item.code: item for item in experiment_service.get_variants(db, experiment.id)}
        for index, variant_spec in enumerate(spec["variants"]):
            if variant_spec["code"] not in existing:
                db.add(
                    Variant(
                        experiment_id=experiment.id,
                        code=variant_spec["code"],
                        name=variant_spec["name"],
                        ratio=variant_spec["ratio"],
                        is_control=variant_spec["is_control"],
                        note=variant_spec.get("note"),
                        sort_order=index,
                    )
                )
        db.flush()
        mapping[spec["code"]] = {item.code: item for item in experiment_service.get_variants(db, experiment.id)}
    return mapping


def ensure_segments(db) -> dict[str, TrafficSegment]:
    """每个实验保证一个 baseline 生效投放段，承接全部 seed 样本与结论（幂等）。"""
    mapping: dict[str, TrafficSegment] = {}
    experiments = db.scalars(select(Experiment)).all()
    for experiment in experiments:
        existing = segment_service.active_segment(db, experiment.id)
        if existing is None:
            segment, _ = segment_service.register_or_get(
                db,
                experiment,
                content_ref="baseline://initial",
                content_payload={"source": "seed", "note": "初始化投放段，承接演示数据"},
                operator_email=SEED_OPERATOR,
            )
            # seed 的 baseline 段直接作为生效段（后续 check 会把完整性补齐并 cutover）
            segment.status = "active"
            segment.is_active = True
            segment.active_slot = experiment.id
            segment.dedup_slot = experiment.id
            segment.activated_at = segment.created_at
            experiment.active_segment_id = segment.id
            existing = segment
        mapping[experiment.code] = existing
    db.flush()
    return mapping


def ensure_assignments(db, variants: dict[str, dict[str, Variant]], segments: dict[str, TrafficSegment]) -> int:
    experiments = {item.code: item for item in db.scalars(select(Experiment)).all()}
    for spec in EXPERIMENTS:
        experiment = experiments.get(spec["code"])
        if experiment is None:
            continue
        segment = segments[spec["code"]]
        for cell in assignment_cells(spec):
            variant = variants[spec["code"]][cell["variant_code"]]
            assignment_service.upsert_assignment(
                db,
                experiment,
                segment=segment,
                variant_id=variant.id,
                channel=cell["channel"],
                metric_key=cell["metric_key"],
                stat_date=cell["stat_date"],
                samples=cell["samples"],
                conversions=cell["conversions"],
                operator_email=SEED_OPERATOR,
            )
    return db.scalar(select(func.count()).select_from(Assignment)) or 0


def run_checks(db, segments: dict[str, TrafficSegment]) -> int:
    experiments = db.scalars(select(Experiment).order_by(Experiment.id)).all()
    for experiment in experiments:
        segment = segments[experiment.code]
        srm_service.check(db, experiment, segment=segment, operator_email=SEED_OPERATOR)
        metric_service.run_checks(
            db,
            experiment,
            method="bh",
            variant_code=None,
            operator_email=SEED_OPERATOR,
            segment=segment,
        )
        # baseline 段样本/校验/指标已齐备，固化为完整且生效
        segment_service.refresh_completeness(db, segment)
        segment.status = "active"
        segment.is_active = True
        if segment.activated_at is None:
            from src.utils.timeutil import utcnow

            segment.activated_at = utcnow()
        experiment.active_segment_id = segment.id
    db.flush()
    return db.scalar(select(func.count()).select_from(MetricResult)) or 0


def ensure_decisions(db, segments: dict[str, TrafficSegment]) -> int:
    experiments = {item.code: item for item in db.scalars(select(Experiment)).all()}
    for code, (verdict, template) in DECISIONS.items():
        experiment = experiments.get(code)
        if experiment is None:
            continue
        existing = decision_service.get_by_experiment(db, experiment.id)
        if existing is not None:
            continue
        segment = segments[code]
        primary = db.scalar(
            select(MetricResult).where(
                MetricResult.segment_id == segment.id,
                MetricResult.is_primary.is_(True),
            )
        )
        context = {
            "chi2": experiment.srm_chi2 or 0.0,
            "p": experiment.srm_p_value or 1.0,
            "c": primary.control_rate if primary else 0.0,
            "v": primary.variant_rate if primary else 0.0,
            "lift": primary.lift if primary else 0.0,
            "q": primary.q_value if primary else 1.0,
        }
        decision = decision_service.create(
            db,
            experiment,
            {"verdict": verdict, "rationale": template.format(**context)},
            decided_by="admin@abcheck.io",
        )
        experiment.status = "finished"
        if decision is not None:
            decision.seed_key = f"seed-decision-{code}"
    db.flush()
    return db.scalar(select(func.count()).select_from(Decision)) or 0


def ensure_audit(db) -> None:
    seeds = [
        ("seed-audit-1", "admin@abcheck.io", "admin", "experiment.create", "experiment", {"code": "EXP-2603-CARTBTN"}),
        ("seed-audit-2", "seed@abcheck.io", "admin", "srm.check", "experiment", {"code": "EXP-2603-CARTBTN", "alarm": True}),
        ("seed-audit-3", "seed@abcheck.io", "admin", "metric.check", "experiment", {"method": "bh"}),
    ]
    for seed_key, email, role, action, entity, detail in seeds:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    with session_scope() as db:
        users = ensure_users(db)
        experiments = ensure_experiments(db)
        variants = ensure_variants(db)
        segments = ensure_segments(db)
        assignments = ensure_assignments(db, variants, segments)
        findings = run_checks(db, segments)
        ensure_decisions(db, segments)
        ensure_audit(db)
        pending = db.scalar(
            select(func.count())
            .select_from(Experiment)
            .where(~Experiment.id.in_(select(Decision.experiment_id).where(Decision.is_valid.is_(True))))
        ) or 0
        summary = (
            f"SEED_SUMMARY brand=abcheck users={users} sources={experiments} "
            f"runs={assignments} findings={findings} pending={pending}"
        )
        print(summary, flush=True)
        return {
            "users": users,
            "sources": experiments,
            "runs": assignments,
            "findings": findings,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()
