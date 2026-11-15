"""实验登记：一次 A/B 实验的元信息 + 最近一次 SRM/功效快照。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(80), default="橙野 App · 增长实验组")
    primary_metric: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    baseline_rate: Mapped[float] = mapped_column(Float, default=0.1)
    planned_mde: Mapped[float] = mapped_column(Float, default=0.01)
    alpha: Mapped[float] = mapped_column(Float, default=0.05)
    power_target: Mapped[float] = mapped_column(Float, default=0.8)
    traffic_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- 算法 A 最近一次快照（POST /experiments/{id}/srm-check 写入）----
    srm_chi2: Mapped[float | None] = mapped_column(Float, nullable=True)
    srm_df: Mapped[int | None] = mapped_column(Integer, nullable=True)
    srm_p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    srm_status: Mapped[str] = mapped_column(String(12), default="unknown")
    srm_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    required_per_variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    power_at_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    mde_at_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    srm_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    has_srm_alarm: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
