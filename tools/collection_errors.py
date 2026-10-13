"""Stable, safe-to-display collection errors; never expose signed URLs/cookies."""

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class CollectionFailure:
    error_code: str
    message: str
    action: str
    retryable: bool = True

    def as_dict(self):
        return asdict(self)


def classify_collection_error(exc):
    text = str(exc).lower()
    code = getattr(exc, "error_code", "")
    if code == "user_stop":
        return CollectionFailure(code, "已安全停止", "已完成的数据保留；点击恢复监控可继续。", False)
    if code == "browser_busy":
        return CollectionFailure(code, "抖音页签忙碌", "等待其他采集任务结束后重试。")
    if any(token in text for token in ("argus", "uifid", "blocked", "风控", "http 403", "http 429")):
        return CollectionFailure("risk_control", "触发风控，请稍后重试", "已暂停后续请求，按递增冷却策略重试。")
    if "login" in text or "登录" in text:
        return CollectionFailure("login_required", "抖音登录已失效", "请在专用 Chrome 中登录抖音，然后恢复监控。")
    if type(exc).__name__ == "DouyinPostUnavailableError":
        return CollectionFailure("post_deleted", "作品已删除或不可用", "该作品的后续快照任务已终止。", False)
    if code == "tab_changed" or any(token in text for token in ("页签", "分页状态", "tab changed")):
        return CollectionFailure("tab_changed", "抖音页签已切换或关闭", "请打开专用抖音页签；采集中不要手动跳转。")
    if any(token in text for token in ("target closed", "browser has been closed", "disconnected", "websocket", "cdp", "econnrefused")):
        return CollectionFailure("browser_disconnected", "专用浏览器连接断开", "请确认专用 Chrome 正在运行，再恢复监控。")
    if code == "network_timeout" or any(token in text for token in ("timeout", "timed out", "connection", "err_network", "network", "网络", "超时")) or isinstance(exc, TimeoutError):
        return CollectionFailure("network_timeout", "网络请求失败或超时", "检查专用 Chrome 的网络和代理后重试。")
    if isinstance(exc, ValueError) or any(token in text for token in ("json", "decode", "missing required", "does not match")):
        return CollectionFailure("invalid_response", "返回数据不完整", "未写入异常数据，稍后重试。")
    return CollectionFailure("unknown", "采集暂未完成", "已保留完成的数据，请检查控制台后重试。")
