"""变体服务：按实验读取 / 校验对照组。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.variant import Variant
from src.services.experiment_service import serialize_variant
from src.utils.errors import AppError


def list_variants(db: Session, experiment_id: int) -> list[Variant]:
    return list(
        db.scalars(
            select(Variant).where(Variant.experiment_id == experiment_id).order_by(Variant.sort_order, Variant.id)
        ).all()
    )


def control_variant(db: Session, experiment_id: int) -> Variant:
    variant = db.scalar(select(Variant).where(Variant.experiment_id == experiment_id, Variant.is_control.is_(True)))
    if variant is None:
        raise AppError("VALIDATION", 422, {"reason": "实验缺少对照组变体"})
    return variant


def by_code(db: Session, experiment_id: int, code: str) -> Variant:
    variant = db.scalar(select(Variant).where(Variant.experiment_id == experiment_id, Variant.code == code))
    if variant is None:
        raise AppError("NOT_FOUND", 404, {"entity": "variant", "code": code})
    return variant


def serialize_all(db: Session, experiment_id: int) -> list[dict]:
    return [serialize_variant(item) for item in list_variants(db, experiment_id)]
