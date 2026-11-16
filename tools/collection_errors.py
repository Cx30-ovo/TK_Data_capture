"""Stable, safe-to-display collection errors; never expose signed URLs/cookies."""

from dataclasses import dataclass, asdict
import json
import logging
import re
import sqlite3
import traceback
import uuid


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
    if code == "browser_connection_timeout":
        return CollectionFailure(code, "浏览器控制连接超时", "正在尝试恢复受管采集页；不代表平台请求超时。")
    if isinstance(exc, sqlite3.Error):
        sqlite_code = getattr(exc, "sqlite_errorcode", None)
        if type(sqlite_code) is int and sqlite_code & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return CollectionFailure("storage_busy", "评论存储暂时忙碌", "本次事务已回滚，保留已提交进度；稍后重试，不需重启浏览器。")
        return CollectionFailure("storage_error", "本地存储操作失败", "检查存储诊断和磁盘状态；不将其判为平台风控。")
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


def record_collection_error(exc, *, kind, phase="unknown"):
    """Log locations and exception types, never messages, URLs, locals or cookies."""
    phase = getattr(exc, "storage_phase", getattr(exc, "collection_phase", phase))
    token = lambda value: re.sub(r"[^a-zA-Z0-9_.-]", "_", str(value))[:80]
    diagnostic = getattr(exc, "collection_diagnostic", None)
    if diagnostic is None:
        diagnostic = {"diagnostic_id": uuid.uuid4().hex[:12], "phase": token(phase)}
        chain, seen, current = [], set(), exc
        while current is not None and id(current) not in seen and len(chain) < 5:
            seen.add(id(current))
            frames = [{"file": token(frame.filename.replace("\\", "/").split("/")[-1]),
                       "line": frame.lineno, "function": token(frame.name)}
                      for frame in traceback.extract_tb(current.__traceback__)[-8:]]
            entry = {"type": token(type(current).__name__), "frames": frames}
            if isinstance(current, sqlite3.Error):
                code, name = getattr(current, "sqlite_errorcode", None), getattr(current, "sqlite_errorname", None)
                if type(code) is int and 0 <= code <= 2**31 - 1:
                    entry["sqlite_errorcode"] = code
                if isinstance(name, str) and re.fullmatch(r"SQLITE_[A-Z0-9_]{1,64}", name):
                    entry["sqlite_errorname"] = name
                attempts = getattr(current, "storage_attempts", None)
                if type(attempts) is int and 1 <= attempts <= 3:
                    entry["storage_attempts"] = attempts
            chain.append(entry)
            current = current.__cause__ or current.__context__
        logging.getLogger("MediaCrawler").warning("collection_failure %s", json.dumps(
            {**diagnostic, "kind": token(kind), "error_code": classify_collection_error(exc).error_code,
             "exceptions": chain}, ensure_ascii=False))
        exc.collection_diagnostic = diagnostic
    return dict(diagnostic)
