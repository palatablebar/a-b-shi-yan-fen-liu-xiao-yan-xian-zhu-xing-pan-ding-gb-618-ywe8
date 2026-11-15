"""投放段 SRM 结果：每个投放段一份独立的分流校验/功效快照。

与 experiments 表上的最近快照不同，这里按段固化「分流判断」，
段被顶替后历史 SRM 结论仍可追溯，但不再作为当前决策依据。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class SrmResult(Base):
    __tablename__ = "srm_results"
    __table_args__ = (
        UniqueConstraint("segment_id", name="uq_srm_segment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("traffic_segments.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    chi2: Mapped[float | None] = mapped_column(Float, nullable=True)
    df: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="unknown")
    alarm: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    required_per_variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    power_at_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    mde_at_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_samples: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_by: Mapped[str] = mapped_column(String(160), default="system")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
