"""投放段（traffic segment）领域不变量：内容绑定、幂等、原子切换、失效与完整性闸门。

用 SQLite 内存库验证应用层语义（与方言无关的槽位唯一约束 + 服务层事务逻辑）。
覆盖需求：
- 每次投放内容与样本绑定，同段样本/SRM/指标/决策一致才开放决策；
- 内容变化旧结论立即失效，但新段完整切换前不换决策依据；
- 切换失败保留旧版完整结果，不露出半套新结果；
- 同一次变更重试不重复建段，失败后可就同内容重新登记。
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base
from src.models.decision import Decision
from src.models.srm_result import SrmResult
from src.models.traffic_segment import TrafficSegment
from src.services import (
    assignment_service,
    decision_service,
    experiment_service,
    metric_service,
    segment_service,
    srm_service,
)
from src.utils.errors import AppError


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    db = maker()
    try:
        yield db
    finally:
        db.close()


def _experiment(db, code="EXP-SEG-1"):
    return experiment_service.create_experiment(
        db,
        {
            "code": code,
            "name": "投放段测试",
            "primary_metric": "order_rate",
            "baseline_rate": 0.10,
            "planned_mde": 0.012,
            "variants": [
                {"code": "control", "name": "对照", "ratio": 0.5, "is_control": True},
                {"code": "treat_a", "name": "实验", "ratio": 0.5, "is_control": False},
            ],
        },
        owner_default="tester",
    )


def _feed(db, exp, segment, day, n=3000, rate_t=0.113):
    variants = {v.code: v for v in experiment_service.get_variants(db, exp.id)}
    for vcode, rate in (("control", 0.10), ("treat_a", rate_t)):
        assignment_service.upsert_assignment(
            db, exp, segment=segment, variant_id=variants[vcode].id, channel="feed",
            metric_key="order_rate", stat_date=day, samples=n,
            conversions=int(n * rate), operator_email="tester",
        )


def _build_and_activate(db, exp, segment, day):
    _feed(db, exp, segment, day)
    srm_service.check(db, exp, segment=segment, operator_email="tester")
    metric_service.run_checks(db, exp, segment=segment, operator_email="tester")
    segment_service.cutover(db, exp, segment)
    db.commit()
    return segment


def test_no_active_segment_blocks_assignment(session):
    exp = _experiment(session)
    segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    with pytest.raises(AppError) as exc:
        assignment_service.create_assignment(
            session, exp,
            {"variant_code": "control", "channel": "feed", "metric_key": "order_rate",
             "stat_date": datetime.date(2026, 1, 1), "samples": 10, "conversions": 1},
            operator_email="t",
        )
    assert exc.value.code == "NO_ACTIVE_SEGMENT"


def test_full_cutover_binds_samples_checks_metrics_and_decision(session):
    exp = _experiment(session)
    seg, created = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    assert created and seg.status == "building"
    _build_and_activate(session, exp, seg, datetime.date(2026, 1, 1))

    assert segment_service.active_segment(session, exp.id).id == seg.id
    assert exp.active_segment_id == seg.id
    assert session.scalar(select(func.count()).select_from(SrmResult).where(SrmResult.segment_id == seg.id)) == 1
    decision = decision_service.create(
        session, exp, {"verdict": "ship", "rationale": "显著正向，允许上线"}, decided_by="admin@x.io"
    )
    assert decision.segment_id == seg.id and decision.is_valid and decision.valid_slot == exp.id

    # 同段重复有效决策被 409
    with pytest.raises(AppError) as exc:
        decision_service.create(session, exp, {"verdict": "continue", "rationale": "重复决策应拒绝凑字"}, decided_by="admin@x.io")
    assert exc.value.status_code == 409


def test_content_change_invalidates_decision_but_keeps_basis_until_cutover(session):
    exp = _experiment(session)
    seg1, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    _build_and_activate(session, exp, seg1, datetime.date(2026, 1, 1))
    decision = decision_service.create(
        session, exp, {"verdict": "ship", "rationale": "旧内容上线结论凑够字数"}, decided_by="admin@x.io"
    )

    seg2, created = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"v": 2}, operator_email="t"
    )
    session.commit()
    assert created and seg2.status == "building"
    # 旧段仍是当前依据（不提前切换），但旧结论立即失效，且不能再基于旧内容出决策
    assert segment_service.active_segment(session, exp.id).id == seg1.id
    session.refresh(decision)
    assert decision.is_valid is False and decision.valid_slot is None
    with pytest.raises(AppError) as exc:
        decision_service.create(session, exp, {"verdict": "ship", "rationale": "过渡期不应能上线凑够字数"}, decided_by="admin@x.io")
    assert exc.value.code == "SEGMENT_SUPERSEDED_PENDING"


def test_retry_same_content_does_not_duplicate_segment(session):
    exp = _experiment(session)
    first, created1 = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"a": 1, "b": 2}, operator_email="t"
    )
    again, created2 = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"b": 2, "a": 1}, operator_email="t"
    )
    assert created1 is True and created2 is False
    assert first.id == again.id
    assert session.scalar(select(func.count()).select_from(TrafficSegment)) == 1


def test_failed_cutover_keeps_old_complete_results_and_allows_reregister(session):
    exp = _experiment(session)
    seg1, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    _build_and_activate(session, exp, seg1, datetime.date(2026, 1, 1))

    seg2, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"v": 2}, operator_email="t"
    )
    session.commit()
    seg2_id = seg2.id
    # 无样本 → cutover 完整性失败
    with pytest.raises(AppError) as exc:
        segment_service.cutover(session, exp, session.get(TrafficSegment, seg2_id))
    assert exc.value.code == "SEGMENT_INCOMPLETE"
    session.rollback()
    segment_service.mark_failed(session, session.get(TrafficSegment, seg2_id), "完整性校验失败")
    session.commit()

    # 旧 active 段完整保留；没有半套 SRM 结果
    assert segment_service.active_segment(session, exp.id).id == seg1.id
    assert session.scalar(select(func.count()).select_from(SrmResult).where(SrmResult.segment_id == seg2_id)) == 0

    # 失败后就同一内容可重新登记新候选段（不被唯一约束挡住）
    retry, created = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"v": 2}, operator_email="t"
    )
    session.commit()
    assert created is True and retry.status == "building" and retry.id != seg2_id


def test_segment_data_isolation_and_history_retained(session):
    exp = _experiment(session)
    seg1, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    _build_and_activate(session, exp, seg1, datetime.date(2026, 1, 1))
    decision_service.create(session, exp, {"verdict": "ship", "rationale": "段一结论凑够字数"}, decided_by="admin@x.io")

    seg2, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"v": 2}, operator_email="t"
    )
    session.commit()
    _build_and_activate(session, exp, seg2, datetime.date(2026, 2, 1))

    # 聚合默认只算 active 段（seg2 每变体 3000，两变体合计 6000）
    totals = assignment_service.variant_totals(session, exp)
    assert sum(row["samples"] for row in totals) == 6000
    # 两段指标独立可查，历史不丢
    s1 = metric_service.list_metrics(session, experiment_id=exp.id, segment_id=seg1.id)["total"]
    s2 = metric_service.list_metrics(session, experiment_id=exp.id, segment_id=seg2.id)["total"]
    assert s1 >= 1 and s2 >= 1
    assert metric_service.list_metrics(session, experiment_id=exp.id)["total"] == s1 + s2
    # 旧段已顶替，旧决策失效但保留；当前可基于新段出新决策
    assert session.get(TrafficSegment, seg1.id).status == "superseded"
    assert session.scalar(select(func.count()).select_from(Decision)) == 1
    new_decision = decision_service.create(
        session, exp, {"verdict": "continue", "rationale": "新段继续观察凑够字数"}, decided_by="admin@x.io"
    )
    assert new_decision.segment_id == seg2.id and new_decision.is_valid
    assert session.scalar(
        select(func.count()).select_from(Decision).where(Decision.is_valid.is_(True))
    ) == 1


def test_cutover_is_idempotent(session):
    exp = _experiment(session)
    seg, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    _build_and_activate(session, exp, seg, datetime.date(2026, 1, 1))
    again = segment_service.cutover(session, exp, seg)
    assert again.id == seg.id and again.status == "active"
    assert session.scalar(select(func.count()).select_from(TrafficSegment)) == 1


def test_closed_segment_rejects_new_samples(session):
    exp = _experiment(session)
    seg1, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v1", content_payload={"v": 1}, operator_email="t"
    )
    _build_and_activate(session, exp, seg1, datetime.date(2026, 1, 1))
    # 新内容把 seg1 顶替为 superseded
    seg2, _ = segment_service.register_or_get(
        session, exp, content_ref="page-v2", content_payload={"v": 2}, operator_email="t"
    )
    session.commit()
    _build_and_activate(session, exp, seg2, datetime.date(2026, 2, 1))
    session.refresh(seg1)
    assert seg1.status == "superseded"
    with pytest.raises(AppError) as exc:
        assignment_service.create_assignment(
            session, exp,
            {"variant_code": "control", "channel": "feed", "metric_key": "order_rate",
             "stat_date": datetime.date(2026, 3, 1), "samples": 10, "conversions": 1},
            operator_email="t", segment_id=seg1.id,
        )
    assert exc.value.code == "SEGMENT_CLOSED"
