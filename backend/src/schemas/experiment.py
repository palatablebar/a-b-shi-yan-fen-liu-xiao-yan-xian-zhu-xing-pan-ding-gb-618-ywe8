from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.constants.enums import Channel, ExperimentStatus, MetricKey

STATUS_VALUES = tuple(item.value for item in ExperimentStatus)
METRIC_VALUES = tuple(item.value for item in MetricKey)
CHANNEL_VALUES = tuple(item.value for item in Channel)


class VariantIn(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    ratio: float = Field(gt=0, le=1)
    is_control: bool = False
    note: str | None = Field(default=None, max_length=500)


class ExperimentIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    hypothesis: str = Field(default="", max_length=2000)
    owner: str | None = Field(default=None, max_length=80)
    primary_metric: str = Field(default="order_rate")
    status: str = "running"
    baseline_rate: float = Field(default=0.1, gt=0, lt=1)
    planned_mde: float = Field(default=0.01, gt=0, le=0.5)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    power_target: float = Field(default=0.8, gt=0, lt=1)
    traffic_note: str | None = Field(default=None, max_length=500)
    started_on: date | None = None
    ended_on: date | None = None
    variants: list[VariantIn] = Field(default_factory=list, min_length=2, max_length=4)

    @field_validator("primary_metric")
    @classmethod
    def _metric_ok(cls, value: str) -> str:
        if value not in METRIC_VALUES:
            raise ValueError(f"primary_metric 必须是 {METRIC_VALUES} 之一")
        return value

    @field_validator("status")
    @classmethod
    def _status_ok(cls, value: str) -> str:
        if value not in STATUS_VALUES:
            raise ValueError(f"status 必须是 {STATUS_VALUES} 之一")
        return value

    @field_validator("variants")
    @classmethod
    def _variants_ok(cls, value: list[VariantIn]) -> list[VariantIn]:
        codes = [item.code for item in value]
        if len(set(codes)) != len(codes):
            raise ValueError("变体编码不能重复")
        if sum(1 for item in value if item.is_control) != 1:
            raise ValueError("必须有且只有一个对照组")
        total = sum(item.ratio for item in value)
        if abs(total - 1.0) > 0.02:
            raise ValueError(f"计划分流比例合计应约等于 1，当前 {total:.3f}")
        return value


class ExperimentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    hypothesis: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=80)
    status: Literal["draft", "running", "paused", "finished", "archived"] | None = None
    baseline_rate: float | None = Field(default=None, gt=0, lt=1)
    planned_mde: float | None = Field(default=None, gt=0, le=0.5)
    alpha: float | None = Field(default=None, gt=0, lt=0.5)
    power_target: float | None = Field(default=None, gt=0, lt=1)
    traffic_note: str | None = Field(default=None, max_length=500)


class SrmCheckIn(BaseModel):
    alpha: float | None = Field(default=None, gt=0, lt=0.5)
    power: float | None = Field(default=None, gt=0, lt=1)
    alarm_p: float | None = Field(default=None, gt=0, lt=0.5)


class MetricCheckIn(BaseModel):
    method: Literal["bh", "bonferroni"] = "bh"
    alpha: float | None = Field(default=None, gt=0, lt=0.5)
    variant_code: str | None = Field(default=None, max_length=40)
