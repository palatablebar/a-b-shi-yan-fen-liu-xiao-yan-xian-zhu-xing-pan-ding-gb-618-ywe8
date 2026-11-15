from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.constants.enums import Channel, MetricKey

CHANNEL_VALUES = tuple(item.value for item in Channel)
METRIC_VALUES = tuple(item.value for item in MetricKey)


class AssignmentIn(BaseModel):
    variant_code: str = Field(min_length=2, max_length=40)
    channel: Literal["feed", "push", "search", "mp"]
    metric_key: Literal["cart_rate", "order_rate", "retention_d1", "click_rate", "search_success"]
    stat_date: date
    samples: int = Field(ge=0, le=50_000_000)
    conversions: int = Field(ge=0, le=50_000_000)

    @model_validator(mode="after")
    def _conversions_not_more_than_samples(self) -> "AssignmentIn":
        if self.conversions > self.samples:
            raise ValueError("转化数不能大于样本数")
        return self


class AssignmentBatchIn(BaseModel):
    items: list[AssignmentIn] = Field(min_length=1, max_length=500)
