"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，各项目的展示名与职责不同。
本项目的分工（源自 batch-plan gb-618）：
  admin   实验负责人：建实验、录分流样本、跑 SRM/指标检验、出决策、导出、看审计
  analyst 数据分析师：看实验台账/样本/检验结果，可导出报表；不能改实验或出决策
  viewer  只读：只能看列表与详情，导出与审计一律 403
"""
from __future__ import annotations

from src.constants.enums import Role

DEFAULT_OWNER = "橙野 App · 增长实验组"

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "实验负责人",
    Role.ANALYST.value: "数据分析师",
    Role.VIEWER.value: "业务只读",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "登记实验与变体、录入分流样本、跑 SRM 与指标检验、出决策、导出报表",
    Role.ANALYST.value: "查看分流样本与检验结果、复核口径、导出分析报表",
    Role.VIEWER.value: "只读查看实验台账、分流与检验结果，不能导出",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "experiment:read", "experiment:write",
        "assignment:read", "assignment:write",
        "srm:read", "srm:run",
        "metric:read", "metric:run",
        "decision:read", "decision:write",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "experiment:read", "assignment:read", "srm:read", "metric:read",
        "decision:read", "export:read", "overview:read",
    },
    Role.VIEWER.value: {
        "experiment:read", "assignment:read", "srm:read", "metric:read",
        "decision:read", "overview:read",
    },
}

EXPERIMENT_WRITE_ROLES = (Role.ADMIN.value,)
ASSIGNMENT_WRITE_ROLES = (Role.ADMIN.value,)
CHECK_ROLES = (Role.ADMIN.value,)
DECISION_ROLES = (Role.ADMIN.value,)
EXPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())
