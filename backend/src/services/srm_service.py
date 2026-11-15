"""算法 A 的落库层：从 assignments 聚合分流样本 → 跑 SRM/功效 → 写实验快照。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.experiment import Experiment
from src.services import assignment_service
from src.services.algorithms import srm as srm_algorithm
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, utcnow


def build_variants(db: Session, experiment: Experiment) -> list[dict]:
    totals = assignment_service.variant_totals(db, experiment)
    return [
        {
            "code": row["code"],
            "name": row["name"],
            "ratio": row["ratio"],
            "observed": row["samples"],
            "is_control": row["is_control"],
            "conversions": row["conversions"],
        }
        for row in totals
    ]


def check(
    db: Session,
    experiment: Experiment,
    *,
    alpha: float | None = None,
    power: float | None = None,
    alarm_p: float | None = None,
) -> dict:
    variants = build_variants(db, experiment)
    if sum(item["observed"] for item in variants) <= 0:
        raise AppError(
            "NO_SAMPLES",
            422,
            {"reason": "该实验还没有分流样本，先按变体/渠道/日期录入样本再校验", "experiment": experiment.code},
        )
    try:
        result = srm_algorithm.run_srm(
            variants,
            baseline_rate=experiment.baseline_rate,
            planned_mde=experiment.planned_mde,
            alpha=alpha if alpha is not None else experiment.alpha,
            power=power if power is not None else experiment.power_target,
            alarm_p=alarm_p if alarm_p is not None else 0.001,
        )
    except ValueError as exc:
        raise AppError("VALIDATION", 422, {"reason": str(exc)}) from exc

    experiment.srm_chi2 = result["chi2"]
    experiment.srm_df = result["df"]
    experiment.srm_p_value = result["p_value"]
    experiment.srm_status = result["status"]
    experiment.has_srm_alarm = result["alarm"]
    experiment.srm_checked_at = utcnow()
    experiment.required_per_variant = result["required_per_variant"]
    experiment.power_at_current = result["power_at_current"]
    experiment.mde_at_current = result["mde_at_current"]
    experiment.srm_payload = result
    db.flush()
    return snapshot(experiment)


def snapshot(experiment: Experiment) -> dict:
    payload = experiment.srm_payload or {}
    return {
        "experiment_id": experiment.id,
        "experiment_code": experiment.code,
        "status": experiment.srm_status,
        "alarm": experiment.has_srm_alarm,
        "chi2": experiment.srm_chi2,
        "df": experiment.srm_df,
        "p_value": experiment.srm_p_value,
        "checked_at": iso_utc(experiment.srm_checked_at),
        "required_per_variant": experiment.required_per_variant,
        "power_at_current": experiment.power_at_current,
        "mde_at_current": experiment.mde_at_current,
        "baseline_rate": experiment.baseline_rate,
        "planned_mde": experiment.planned_mde,
        "payload": payload,
        "cells": payload.get("cells", []),
        "gap_total": payload.get("gap_total"),
        "note": payload.get("note", ""),
    }
