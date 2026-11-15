from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DecisionIn(BaseModel):
    verdict: Literal["ship", "continue", "stop"]
    rationale: str = Field(min_length=4, max_length=2000)
