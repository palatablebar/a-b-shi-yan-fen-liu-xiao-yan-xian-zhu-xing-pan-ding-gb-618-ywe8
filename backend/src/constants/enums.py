"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class ExperimentStatus(StrEnum):
    """实验生命周期。"""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ARCHIVED = "archived"


EXPERIMENT_STATUS_LABELS: dict[str, str] = {
    ExperimentStatus.DRAFT.value: "草稿",
    ExperimentStatus.RUNNING.value: "运行中",
    ExperimentStatus.PAUSED.value: "已暂停",
    ExperimentStatus.FINISHED.value: "已结束",
    ExperimentStatus.ARCHIVED.value: "已归档",
}

EXPERIMENT_STATUS_ORDER: list[str] = [
    ExperimentStatus.RUNNING.value,
    ExperimentStatus.PAUSED.value,
    ExperimentStatus.DRAFT.value,
    ExperimentStatus.FINISHED.value,
    ExperimentStatus.ARCHIVED.value,
]


class Channel(StrEnum):
    """分流渠道：1 个 App 4 个入口。"""

    FEED = "feed"
    PUSH = "push"
    SEARCH = "search"
    MP = "mp"


CHANNEL_LABELS: dict[str, str] = {
    Channel.FEED.value: "信息流",
    Channel.PUSH.value: "推送",
    Channel.SEARCH.value: "搜索",
    Channel.MP.value: "小程序",
}

CHANNEL_ORDER: list[str] = [Channel.FEED.value, Channel.PUSH.value, Channel.SEARCH.value, Channel.MP.value]


class MetricKey(StrEnum):
    """实验可登记的指标口径（与 seed / 前端下拉同步）。"""

    CART = "cart_rate"
    ORDER = "order_rate"
    RETENTION = "retention_d1"
    CLICK = "click_rate"
    SEARCH_SUCCESS = "search_success"


METRIC_LABELS: dict[str, str] = {
    MetricKey.CART.value: "加购转化率",
    MetricKey.ORDER.value: "下单转化率",
    MetricKey.RETENTION.value: "次日留存",
    MetricKey.CLICK.value: "点击率",
    MetricKey.SEARCH_SUCCESS.value: "搜索成功率",
}


class Verdict(StrEnum):
    """决策结论。"""

    SHIP = "ship"
    CONTINUE = "continue"
    STOP = "stop"


VERDICT_LABELS: dict[str, str] = {
    Verdict.SHIP.value: "上线",
    Verdict.CONTINUE.value: "继续观察",
    Verdict.STOP.value: "停止",
}

VERDICT_ORDER: list[str] = [Verdict.SHIP.value, Verdict.CONTINUE.value, Verdict.STOP.value]


class SrmStatus(StrEnum):
    """分流健康度。"""

    BALANCED = "balanced"
    ALARM = "srm"
    UNKNOWN = "unknown"


SRM_STATUS_LABELS: dict[str, str] = {
    SrmStatus.BALANCED.value: "分流均衡",
    SrmStatus.ALARM.value: "SRM 告警",
    SrmStatus.UNKNOWN.value: "未校验",
}


class CorrectionMethod(StrEnum):
    """多重比较校正方法。"""

    BH = "bh"
    BONFERRONI = "bonferroni"


CORRECTION_LABELS: dict[str, str] = {
    CorrectionMethod.BH.value: "BH-FDR",
    CorrectionMethod.BONFERRONI.value: "Bonferroni",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}
