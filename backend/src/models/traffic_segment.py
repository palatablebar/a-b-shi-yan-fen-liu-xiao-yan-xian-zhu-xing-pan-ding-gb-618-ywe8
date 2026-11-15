"""投放段（traffic segment）：一次「实际投放内容」与它名下样本/校验/指标/决策的绑定边界。

口径：
- 同一实验的每一次实际投放内容（content_ref + content_hash）对应一个投放段；
- 同一次变更的重复登记/重试不会新建投放段（dedup_slot + content_hash 幂等）；
- 同一时刻一个实验至多一个 active 段，决策只允许基于 active 且无更新内容在途的段；
- 上游内容变化 → 旧有效决策立即失效，但旧 active 段保留为决策依据直到新段 cutover 成功；
- 新段必须样本、SRM、指标三段完整计算并 cutover 成功才成为 active；
  cutover 失败时 building 段标记 failed，旧 active 段及其完整结果继续生效，不露出半套结果；
- 失败后允许就同一内容重新登记新的候选段（failed 段不占幂等槽位）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow

# building：新投放段，样本/校验/指标尚未齐备，不对外作为决策依据
# active：当前唯一生效的投放段，页面、导出、决策全部以它为准
# superseded：上游内容变化后被新段顶替，保留历史但结论立即失效
# failed：cutover 时完整性校验失败，整段作废，旧 active 段继续生效
SEGMENT_BUILDING = "building"
SEGMENT_ACTIVE = "active"
SEGMENT_SUPERSEDED = "superseded"
SEGMENT_FAILED = "failed"

SEGMENT_STATUSES = (SEGMENT_BUILDING, SEGMENT_ACTIVE, SEGMENT_SUPERSEDED, SEGMENT_FAILED)


class TrafficSegment(Base):
    __tablename__ = "traffic_segments"
    __table_args__ = (
        # 仅 building/active 段占槽（dedup_slot 非空），failed/superseded 置 NULL 后不参与唯一约束
        UniqueConstraint("dedup_slot", "content_hash", name="uq_segment_live_content"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    segment_code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    # 实际投放内容身份：人读引用（页面版本/物料号）+ 规范化指纹（判变化、做幂等）
    content_ref: Mapped[str] = mapped_column(String(200), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_summary: Mapped[str] = mapped_column(Text, default="")
    content_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(16), default=SEGMENT_BUILDING, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 唯一槽位：仅 active 段填 experiment_id，其余为 NULL。
    # 利用唯一索引允许多个 NULL 的特性，保证「同实验至多一个 active 段」（MySQL/PG 通用）。
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    # 幂等槽位：building/active 段填 experiment_id，failed/superseded 置 NULL；
    # 配合 (dedup_slot, content_hash) 唯一索引，保证同一次变更重试不重复建段、失败后可重新登记。
    dedup_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # 完整性账本：四项齐备才允许 cutover；任何一项缺失都不得露出为决策依据
    samples_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    srm_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    complete: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ready_reason: Mapped[str] = mapped_column(String(300), default="")

    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
