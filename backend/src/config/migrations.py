"""轻量幂等 schema 兼容迁移。

项目用 ``Base.metadata.create_all`` 建表，不会改已存在的表。本模块在启动建表后执行，
用 SQLAlchemy 通用 Inspector + 方言原生 DDL 补齐投放段特性需要的列与索引，保证：
- 全新库：create_all 直接得到完整结构，迁移全部跳过；
- 已存在的旧库：补列、替换变化的唯一约束、建立槽位唯一索引；
- 可重复执行：每步先查现存列/索引，存在即跳过。

只做增量、不做破坏性数据搬迁；历史数据的段回填在 segment_service.ensure_baseline_segments。
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from src.config.database import engine
from src.config.settings import settings

logger = logging.getLogger("abcheck.migrations")


def _inspector(conn):
    return inspect(conn)


def _column_exists(conn, table: str, column: str) -> bool:
    return column in {col["name"] for col in _inspector(conn).get_columns(table)}


def _add_column(conn, table: str, column: str, ddl_type: str, default_ddl: str = "NULL") -> None:
    if _column_exists(conn, table, column):
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type} {default_ddl}"))
    logger.info("migrate: added %s.%s", table, column)


def _index_exists(conn, index: str) -> bool:
    inspector = _inspector(conn)
    for table in inspector.get_table_names():
        if index in {item["name"] for item in inspector.get_indexes(table)}:
            return True
    return False


def _drop_index_if_exists(conn, index: str, table: str) -> None:
    if not _index_exists(conn, index):
        return
    if settings.db_kind == "mysql":
        conn.execute(text(f"ALTER TABLE {table} DROP INDEX {index}"))
    else:
        conn.execute(text(f"DROP INDEX IF EXISTS {index}"))
    logger.info("migrate: dropped index %s", index)


def run_compat_migrations() -> None:
    with engine.begin() as conn:
        # ---- 新列 -----------------------------------------------------------------
        _add_column(conn, "experiments", "active_segment_id", "INT")
        _add_column(conn, "assignments", "segment_id", "INT")
        _add_column(conn, "metric_results", "segment_id", "INT")
        _add_column(conn, "decisions", "segment_id", "INT")
        _add_column(conn, "decisions", "is_valid", "TINYINT(1)", "NOT NULL DEFAULT 1")
        _add_column(conn, "decisions", "valid_slot", "INT")
        _add_column(conn, "decisions", "invalid_reason", "VARCHAR(300)", "NOT NULL DEFAULT ''")
        _add_column(conn, "traffic_segments", "active_slot", "INT")
        _add_column(conn, "traffic_segments", "dedup_slot", "INT")

        # ---- 外键（旧库补建；存在即报错被忽略）-----------------------------------
        if settings.db_kind == "mysql":
            for fk_ddl in (
                "ALTER TABLE assignments ADD CONSTRAINT fk_assignment_segment "
                "FOREIGN KEY (segment_id) REFERENCES traffic_segments(id) ON DELETE CASCADE",
                "ALTER TABLE metric_results ADD CONSTRAINT fk_metric_segment "
                "FOREIGN KEY (segment_id) REFERENCES traffic_segments(id) ON DELETE CASCADE",
                "ALTER TABLE decisions ADD CONSTRAINT fk_decision_segment "
                "FOREIGN KEY (segment_id) REFERENCES traffic_segments(id) ON DELETE CASCADE",
            ):
                try:
                    conn.execute(text(fk_ddl))
                except Exception as exc:  # noqa: BLE001 - 已存在/重复则跳过
                    logger.debug("skip fk: %s", exc)

        # ---- 替换变化的唯一约束 --------------------------------------------------
        # assignments：自然键加入 segment_id（旧约束按 experiment_id 起头）
        _drop_index_if_exists(conn, "uq_assignment_cell", "assignments")
        if not _index_exists(conn, "uq_assignment_cell"):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_assignment_cell ON assignments "
                    "(segment_id, variant_id, channel, metric_key, stat_date)"
                )
            )
        # metric_results：唯一键由 experiment_id 换成 segment_id
        _drop_index_if_exists(conn, "uq_metric_experiment_variant_metric", "metric_results")
        if not _index_exists(conn, "uq_metric_experiment_variant_metric"):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_metric_experiment_variant_metric ON metric_results "
                    "(segment_id, variant_code, metric_key)"
                )
            )
        # decisions：旧的「一实验一决策」全唯一约束让位给「一实验至多一条有效决策」槽位索引
        _drop_index_if_exists(conn, "uq_decision_experiment", "decisions")
        _drop_index_if_exists(conn, "uq_decision_active", "decisions")
        if not _index_exists(conn, "uq_decision_active"):
            conn.execute(text("CREATE UNIQUE INDEX uq_decision_active ON decisions (valid_slot)"))

        # 投放段：旧的 (experiment_id, content_hash) 全唯一约束让位给「仅活跃段占槽」的幂等索引
        _drop_index_if_exists(conn, "uq_segment_experiment_content", "traffic_segments")
        _drop_index_if_exists(conn, "uq_segment_live_content", "traffic_segments")
        if not _index_exists(conn, "uq_segment_live_content"):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_segment_live_content ON traffic_segments "
                    "(dedup_slot, content_hash)"
                )
            )

        # ---- 投放段唯一槽位：同实验至多一个 active 段 -----------------------------
        if not _index_exists(conn, "uq_segment_active_slot"):
            conn.execute(text("CREATE UNIQUE INDEX uq_segment_active_slot ON traffic_segments (active_slot)"))
    logger.info("compat migrations settled")
