from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SegmentRegisterIn(BaseModel):
    """登记一次实际投放内容（上游页面/物料版本）。

    content_ref 是人读版本引用（如 page-v2 / 物料号），content_payload 是参与指纹的完整内容描述；
    两者规范化后的 content_hash 决定是复用旧段还是开新段，重试提交天然幂等。
    """

    content_ref: str = Field(min_length=2, max_length=200)
    content_summary: str | None = Field(default=None, max_length=500)
    content_payload: dict[str, Any] = Field(default_factory=dict)
    # 可选：显式指定在哪个 building 段上继续录样本/校验（默认当前 active 段）
    segment_id: int | None = None


class SegmentCutoverIn(BaseModel):
    segment_id: int | None = None
