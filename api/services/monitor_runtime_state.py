"""Atomic non-secret runtime state; no database schema changes or GET writes."""

import json
import math
import os
import tempfile
from pathlib import Path


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid monitor runtime number")
    return value


def load(path):
    path = Path(path)
    if not path.exists():
        return None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Monitor runtime state too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or type(data.get("paused")) is not bool:
        raise ValueError("Invalid monitor runtime state")
    for name in ("cooldown_until", "risk_failures"):
        _number(data[name])
    recovery = data["recovery"]
    if not isinstance(recovery, dict) or recovery["state"] not in ("healthy", "waiting", "recovering", "login_required"):
        raise ValueError("Invalid recovery state")
    for name in ("pending", "reset_page"):
        if type(recovery[name]) is not bool:
            raise ValueError("Invalid recovery flag")
    for name in ("attempts", "timeouts", "retry_at"):
        _number(recovery[name])
    retries = data["discovery_retries"]
    if not isinstance(retries, dict):
        raise ValueError("Invalid discovery retries")
    for retry in retries.values():
        if not isinstance(retry, dict):
            raise ValueError("Invalid discovery retry")
        _number(retry["attempts"])
        _number(retry["until"])
        if not isinstance(retry.get("error_code"), str):
            raise ValueError("Invalid retry error code")
    return data


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
