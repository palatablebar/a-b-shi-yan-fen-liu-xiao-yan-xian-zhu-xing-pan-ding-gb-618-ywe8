"""角色白名单与参数校验单测（不依赖数据库）。"""
from __future__ import annotations

from src.constants.roles import (
    AUDIT_ROLES,
    CHECK_ROLES,
    DECISION_ROLES,
    EXPORT_ROLES,
    EXPERIMENT_WRITE_ROLES,
    has_permission,
)
from src.schemas.experiment import ExperimentIn


def test_viewer_cannot_write_export_audit():
    from src.constants.enums import Role

    assert Role.VIEWER.value not in EXPORT_ROLES
    assert Role.VIEWER.value not in AUDIT_ROLES
    assert Role.VIEWER.value not in EXPERIMENT_WRITE_ROLES
    assert Role.VIEWER.value not in CHECK_ROLES
    assert Role.VIEWER.value not in DECISION_ROLES
    assert has_permission("viewer", "metric:read") is True
    assert has_permission("viewer", "metric:run") is False


def test_analyst_can_export_not_audit():
    assert "analyst" in EXPORT_ROLES
    assert "analyst" not in AUDIT_ROLES
    assert "analyst" not in CHECK_ROLES
    assert has_permission("analyst", "export:read") is True
    assert has_permission("analyst", "audit:read") is False


def test_experiment_payload_validation():
    good = {
        "code": "EXP-2615-NEW",
        "name": "商品卡图片比例",
        "primary_metric": "order_rate",
        "variants": [
            {"code": "control", "name": "对照", "ratio": 0.5, "is_control": True},
            {"code": "treat_a", "name": "实验", "ratio": 0.5, "is_control": False},
        ],
    }
    payload = ExperimentIn(**good)
    assert len(payload.variants) == 2

    try:
        ExperimentIn(**{**good, "code": "x"})
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("短 code 应该校验失败")

    try:
        ExperimentIn(**{**good, "variants": [{"code": "a", "name": "甲", "ratio": 1.0, "is_control": False}]})
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("缺对照组应该校验失败")
