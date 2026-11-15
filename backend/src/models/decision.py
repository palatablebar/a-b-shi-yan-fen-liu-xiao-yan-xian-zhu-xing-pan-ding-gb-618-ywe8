"""决策：结论绑定到具体投放段。

口径：
- 一条决策只对应一个投放段（segment_id），页面/导出必须同时展示投放内容；
- 同一实验同时只允许一条「有效」决策（部分唯一索引 uq_decision_active，DDL 见 config/app.py）；
- 上游投放内容变化、旧段被顶替时，旧决策 is_valid 立即置 0（历史保留、结论失效）；
- 新段未完整 cutover 前不得建立新决策，避免负责人依据半套结果上线。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("traffic_segments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # 唯一槽位：仅有效决策填 experiment_id，失效后置 NULL；同实验至多一条有效决策（NULL 不冲突）。
    valid_slot: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    invalid_reason: Mapped[str] = mapped_column(String(300), default="")
    decided_by: Mapped[str] = mapped_column(String(160), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
