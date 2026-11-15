"""演示数据（橙野 App · 增长实验组）：6 个实验 / 13 个变体 / 4 渠道 / 7 天分流样本。

数值口径对齐 batch-plan gb-618 的验收场景：
  EXP-2603-CARTBTN  50/50 计划，实测 52.3% / 47.7%（合计 6,000）→ χ²=12.696, p=0.000366 → SRM 告警
  EXP-2610-CASH8    10.10% vs 11.20%（10,200 / 10,208）→ lift 10.9%，BH 校正后显著 → 上线
其余实验覆盖「显著负向 → 停止」「不显著 → 继续观察」「未决策 → 待决策」。
所有分布由固定权重 + 向下取整 + 余数分配生成，逐次运行完全一致。
"""
from __future__ import annotations

import math
from datetime import date, timedelta

DEMO_PASSWORD = "Demo@2026"

DEMO_USERS = [
    ("admin@abcheck.io", "林可 · 实验负责人", "admin"),
    ("analyst@abcheck.io", "周棠 · 数据分析师", "analyst"),
    ("viewer@abcheck.io", "陈默 · 业务只读", "viewer"),
]

ORG = "橙野 App · 增长实验组"

# 渠道权重（1 个 App 4 个入口）
CHANNEL_WEIGHTS = {"feed": 0.38, "push": 0.24, "search": 0.20, "mp": 0.18}
# 7 天节奏：周中高、周末略低
DAY_WEIGHTS = [0.86, 0.93, 1.01, 1.03, 1.07, 1.10, 1.00]

EXPERIMENTS = [
    {
        "code": "EXP-2603-CARTBTN",
        "name": "购物车按钮文案改版",
        "hypothesis": "「去结算」比「去购物车」少一次决策，下单转化率提升 1pp。",
        "primary_metric": "order_rate",
        "status": "running",
        "baseline_rate": 0.101,
        "planned_mde": 0.011,
        "started_on": date(2026, 3, 2),
        "traffic_note": "计划 50/50；上游分流服务按 device_id 哈希，历史上有过 SDK 版本不均。",
        "variants": [
            {"code": "control", "name": "对照：去购物车", "ratio": 0.5, "is_control": True, "note": "线上原样"},
            {"code": "treat_short", "name": "实验：去结算", "ratio": 0.5, "is_control": False, "note": "短文案"},
        ],
        "targets": {"control": 3138, "treat_short": 2862},
        "rates": {
            "cart_rate": {"control": 0.188, "treat_short": 0.192},
            "order_rate": {"control": 0.101, "treat_short": 0.103},
            "retention_d1": {"control": 0.302, "treat_short": 0.297},
        },
    },
    {
        "code": "EXP-2610-CASH8",
        "name": "结算页「立减 8 元」标签",
        "hypothesis": "把满减信息前置到结算按钮上方，下单转化率提升 1.1pp。",
        "primary_metric": "order_rate",
        "status": "running",
        "baseline_rate": 0.101,
        "planned_mde": 0.012,
        "started_on": date(2026, 6, 1),
        "traffic_note": "50/50 均衡分流，7 天累计 20,408 份样本；口径与 exp-2603 一致。",
        "variants": [
            {"code": "control", "name": "对照：无标签", "ratio": 0.5, "is_control": True, "note": ""},
            {"code": "treat_flat", "name": "实验：立减 8 元", "ratio": 0.5, "is_control": False, "note": "芥末黄标签"},
        ],
        "targets": {"control": 10200, "treat_flat": 10208},
        "rates": {
            "order_rate": {"control": 0.101, "treat_flat": 0.1121},
            "cart_rate": {"control": 0.170, "treat_flat": 0.175},
            "retention_d1": {"control": 0.311, "treat_flat": 0.306},
            "click_rate": {"control": 0.213, "treat_flat": 0.219},
        },
    },
    {
        "code": "EXP-2611-PUSH3",
        "name": "推送文案三选一",
        "hypothesis": "带角标的推送比纯文案点击率高 1pp 以上。",
        "primary_metric": "click_rate",
        "status": "running",
        "baseline_rate": 0.048,
        "planned_mde": 0.013,
        "started_on": date(2026, 5, 11),
        "traffic_note": "三组均分 34/33/33，推送队列按小时切片。",
        "variants": [
            {"code": "control", "name": "对照：原推送", "ratio": 0.3334, "is_control": True, "note": ""},
            {"code": "treat_badge", "name": "实验：带角标", "ratio": 0.3333, "is_control": False, "note": "红点角标"},
            {"code": "treat_emoji", "name": "实验：表情符号", "ratio": 0.3333, "is_control": False, "note": "结尾加 emoji"},
        ],
        "targets": {"control": 4000, "treat_badge": 4002, "treat_emoji": 3998},
        "rates": {
            "click_rate": {"control": 0.048, "treat_badge": 0.062, "treat_emoji": 0.044},
            "order_rate": {"control": 0.021, "treat_badge": 0.026, "treat_emoji": 0.020},
            "retention_d1": {"control": 0.288, "treat_badge": 0.291, "treat_emoji": 0.285},
        },
    },
    {
        "code": "EXP-2612-WELCOME",
        "name": "新客 7 天礼包",
        "hypothesis": "新客礼包能拉高次日留存 1.5pp。",
        "primary_metric": "retention_d1",
        "status": "running",
        "baseline_rate": 0.281,
        "planned_mde": 0.015,
        "started_on": date(2026, 5, 18),
        "traffic_note": "50/50；礼包成本 6.2 元/人。",
        "variants": [
            {"code": "control", "name": "对照：无礼包", "ratio": 0.5, "is_control": True, "note": ""},
            {"code": "treat_gift", "name": "实验：7 天礼包", "ratio": 0.5, "is_control": False, "note": "每日一张券"},
        ],
        "targets": {"control": 8000, "treat_gift": 8000},
        "rates": {
            "retention_d1": {"control": 0.281, "treat_gift": 0.259},
            "order_rate": {"control": 0.062, "treat_gift": 0.058},
            "cart_rate": {"control": 0.141, "treat_gift": 0.138},
        },
    },
    {
        "code": "EXP-2613-FEEDSORT",
        "name": "信息流排序权重",
        "hypothesis": "把关注内容权重从 0.6 提到 0.75，点击率提升 0.5pp。",
        "primary_metric": "click_rate",
        "status": "paused",
        "baseline_rate": 0.083,
        "planned_mde": 0.005,
        "started_on": date(2026, 6, 8),
        "traffic_note": "50/50；因埋点延迟暂停 1 天，样本量未补足。",
        "variants": [
            {"code": "control", "name": "对照：权重 0.6", "ratio": 0.5, "is_control": True, "note": ""},
            {"code": "treat_weight", "name": "实验：权重 0.75", "ratio": 0.5, "is_control": False, "note": ""},
        ],
        "targets": {"control": 6000, "treat_weight": 5998},
        "rates": {
            "click_rate": {"control": 0.083, "treat_weight": 0.086},
            "order_rate": {"control": 0.041, "treat_weight": 0.042},
            "retention_d1": {"control": 0.305, "treat_weight": 0.307},
        },
    },
    {
        "code": "EXP-2614-SUGGEST",
        "name": "搜索联想词补全",
        "hypothesis": "联想词覆盖到二级类目后，搜索成功率提升 2pp。",
        "primary_metric": "search_success",
        "status": "running",
        "baseline_rate": 0.612,
        "planned_mde": 0.02,
        "started_on": date(2026, 6, 15),
        "traffic_note": "50/50；待周三决策会确认。",
        "variants": [
            {"code": "control", "name": "对照：热词", "ratio": 0.5, "is_control": True, "note": ""},
            {"code": "treat_suggest", "name": "实验：二级类目联想", "ratio": 0.5, "is_control": False, "note": ""},
        ],
        "targets": {"control": 7500, "treat_suggest": 7502},
        "rates": {
            "search_success": {"control": 0.612, "treat_suggest": 0.641},
            "click_rate": {"control": 0.229, "treat_suggest": 0.235},
        },
    },
]

# 决策（seed 只补缺，不覆盖人工结论）。exp-2613 / exp-2614 故意留空 → pending=2
DECISIONS = {
    "EXP-2603-CARTBTN": ("continue", "SRM χ²={chi2:.2f}、p={p:.6f} < 0.001：对照组分到 52.3%、实验组 47.7%，分流不均，先修分流再评估指标。"),
    "EXP-2610-CASH8": ("ship", "下单转化率 {v:.2%} vs {c:.2%}，lift {lift:.1%}；BH 校正后 q={q:.3f} < 0.05，每变体样本已过功效线，可上线。"),
    "EXP-2611-PUSH3": ("ship", "带角标变体点击率 {v:.2%} vs {c:.2%}（q={q:.3f}）；表情符号变体不显著，只推角标方案。"),
    "EXP-2612-WELCOME": ("stop", "次日留存 {v:.2%} vs {c:.2%}，lift {lift:.1%} 且 q={q:.3f} 显著为负；礼包成本 6.2 元/人，停止。"),
}


def channels() -> list[str]:
    return ["feed", "push", "search", "mp"]


def days(started_on: date) -> list[date]:
    return [started_on + timedelta(days=offset) for offset in range(7)]


def distribute(total: int, start: date) -> list[tuple[str, date, int]]:
    """把变体总样本按 渠道权重 × 日权重 摊到 28 个格子，合计严格等于 total。"""
    slots: list[tuple[str, date, float]] = []
    day_list = days(start)
    for channel in channels():
        for index, day in enumerate(day_list):
            slots.append((channel, day, CHANNEL_WEIGHTS[channel] * DAY_WEIGHTS[index]))
    weight_sum = sum(item[2] for item in slots)
    raw = [total * item[2] / weight_sum for item in slots]
    values = [int(math.floor(value)) for value in raw]
    remainder = total - sum(values)
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - values[index]), index))
    for index in order[:remainder]:
        values[index] += 1
    return [(slots[index][0], slots[index][1], values[index]) for index in range(len(slots))]


def assignment_cells(experiment: dict) -> list[dict]:
    """生成一个实验的全部分流样本行（含每个指标的转化数）。"""
    cells: list[dict] = []
    start = experiment["started_on"]
    for variant in experiment["variants"]:
        code = variant["code"]
        target = experiment["targets"][code]
        for channel, day, samples in distribute(target, start):
            for metric_key, rate_map in experiment["rates"].items():
                rate = rate_map[code]
                cells.append(
                    {
                        "experiment_code": experiment["code"],
                        "variant_code": code,
                        "channel": channel,
                        "metric_key": metric_key,
                        "stat_date": day,
                        "samples": samples,
                        "conversions": int(math.floor(samples * rate + 0.5)),
                    }
                )
    return cells
