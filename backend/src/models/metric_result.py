"""指标检验结果（算法 B 落库）：每个 (实验, 变体, 指标) 一行。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class MetricResult(Base):
    __tablename__ = "metric_results"
    __table_args__ = (
        UniqueConstraint("experiment_id", "variant_code", "metric_key", name="uq_metric_experiment_variant_metric"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="SET NULL"), nullable=True)
    variant_code: Mapped[str] = mapped_column(String(40), index=True)
    variant_name: Mapped[str] = mapped_column(String(120), default="")
    metric_key: Mapped[str] = mapped_column(String(40), index=True)
    metric_name: Mapped[str] = mapped_column(String(80), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    method: Mapped[str] = mapped_column(String(16), default="bh")
    control_n: Mapped[int] = mapped_column(Integer, default=0)
    control_conversions: Mapped[int] = mapped_column(Integer, default=0)
    variant_n: Mapped[int] = mapped_column(Integer, default=0)
    variant_conversions: Mapped[int] = mapped_column(Integer, default=0)
    control_rate: Mapped[float] = mapped_column(Float, default=0.0)
    variant_rate: Mapped[float] = mapped_column(Float, default=0.0)
    diff: Mapped[float] = mapped_column(Float, default=0.0)
    z: Mapped[float] = mapped_column(Float, default=0.0)
    p_value: Mapped[float] = mapped_column(Float, default=1.0)
    q_value: Mapped[float] = mapped_column(Float, default=1.0)
    q_bh: Mapped[float] = mapped_column(Float, default=1.0)
    q_bonferroni: Mapped[float] = mapped_column(Float, default=1.0)
    ci_low: Mapped[float] = mapped_column(Float, default=0.0)
    ci_high: Mapped[float] = mapped_column(Float, default=0.0)
    lift: Mapped[float] = mapped_column(Float, default=0.0)
    lift_ci_low: Mapped[float] = mapped_column(Float, default=0.0)
    lift_ci_high: Mapped[float] = mapped_column(Float, default=0.0)
    significant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verdict: Mapped[str] = mapped_column(String(16), default="continue", index=True)
    required_n: Mapped[int] = mapped_column(Integer, default=0)
    power_at_current: Mapped[float] = mapped_column(Float, default=0.0)
    alpha: Mapped[float] = mapped_column(Float, default=0.05)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    computed_by: Mapped[str] = mapped_column(String(160), default="system")
