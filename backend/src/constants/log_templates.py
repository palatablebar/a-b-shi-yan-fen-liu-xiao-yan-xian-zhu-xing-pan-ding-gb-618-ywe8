"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "experiment.create": "登记实验",
    "experiment.update": "修改实验",
    "assignment.create": "录入分流样本",
    "assignment.update": "更新分流样本",
    "srm.check": "跑 SRM 校验",
    "metric.check": "跑指标检验",
    "decision.create": "出决策",
    "export.experiments": "导出实验台账",
    "export.assignments": "导出分流样本",
    "export.metrics": "导出指标检验",
    "export.decisions": "导出决策清单",
    "http.mutation": "写请求",
}
