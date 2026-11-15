from __future__ import annotations

from pydantic import BaseModel


class MetricQuery(BaseModel):
    experiment_id: int | None = None
    variant_code: str | None = None
    significant: bool | None = None
    q: str | None = None
