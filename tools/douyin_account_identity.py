"""Validate public Douyin account identities without requesting the platform."""

import re
from urllib.parse import urlsplit


def parse_account_identity(value: str) -> str:
    value = value.strip()
    if "://" in value:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if url.scheme not in ("http", "https") or host not in ("douyin.com", "www.douyin.com"):
            raise ValueError("请填写抖音账号主页链接或账号 ID。")
        match = re.fullmatch(r"/user/([A-Za-z0-9_-]{6,255})/?", url.path)
        if not match:
            raise ValueError("请填写 /user/ 开头的账号主页，不能使用搜索页或作品链接。")
        return match[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,255}", value):
        raise ValueError("账号 ID 格式无效，请复制抖音账号主页链接。")
    return value


def normalize_account_profile(sec_user_id: str, profile_url: str = "") -> tuple[str, str]:
    identity = parse_account_identity(sec_user_id)
    if profile_url and parse_account_identity(profile_url) != identity:
        raise ValueError("主页链接与账号 ID 不一致。")
    return identity, f"https://www.douyin.com/user/{identity}"
