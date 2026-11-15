"""统一业务异常：{code, message, detail}。"""
from __future__ import annotations

ERROR_MESSAGES: dict[str, str] = {
    "AUTH_MISSING": "请先登录",
    "AUTH_INVALID": "账号或密码不正确",
    "FORBIDDEN": "当前角色没有该操作权限",
    "NOT_FOUND": "资源不存在",
    "VALIDATION": "请求参数不合法",
    "CONFLICT": "数据冲突，请刷新后重试",
    "RATE_LIMITED": "请求过于频繁，请稍后再试",
    "INTERNAL": "服务内部错误",
    "NO_SAMPLES": "该投放段还没有分流样本",
    "NO_ACTIVE_SEGMENT": "实验还没有生效投放段，先登记投放内容并完成切换",
    "NO_BUILDING_SEGMENT": "没有构建中的投放段，先登记新的投放内容",
    "SEGMENT_NOT_ACTIVE": "该投放段尚未生效，完整切换前不能作为决策依据",
    "SEGMENT_INCOMPLETE": "投放段结果不完整，样本/分流判断/全部指标齐备后才开放决策",
    "SEGMENT_FAILED": "该投放段切换失败已作废，请基于当前内容重新登记",
    "SEGMENT_SUPERSEDED_PENDING": "上游投放内容已变化，旧结论已失效，等新投放段完整切换后再决策",
    "SEGMENT_CLOSED": "该投放段已封闭（已顶替或切换失败），不能再写入样本",
}


class AppError(Exception):
    def __init__(self, code: str, status_code: int = 400, detail: dict | None = None, message: str | None = None):
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}
        self.message = message or ERROR_MESSAGES.get(code, code)
        super().__init__(self.message)


def bad_request(code: str = "VALIDATION", detail: dict | None = None) -> AppError:
    return AppError(code, 400, detail)


def not_found(entity: str, entity_id: object = None) -> AppError:
    return AppError("NOT_FOUND", 404, {"entity": entity, "id": entity_id})


def forbidden(detail: dict | None = None) -> AppError:
    return AppError("FORBIDDEN", 403, detail)
