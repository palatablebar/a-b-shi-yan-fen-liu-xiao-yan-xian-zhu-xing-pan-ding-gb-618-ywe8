"""实验变体：对照组 / 实验组的计划分流比例。"""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (UniqueConstraint("experiment_id", "code", name="uq_variants_experiment_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    ratio: Mapped[float] = mapped_column(Float, default=0.5)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
