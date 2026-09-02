"""readiness 依赖检查。

依赖地址通过环境变量注入，未配置时服务保持“可单独启动”的本地开发体验；
接入 Compose 后再让 order → payment → promo 形成真实依赖链。
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ReadinessCheck:
    """一次 readiness 检查：name 用于展示，check 返回 (是否通过, 摘要)。"""

    name: str
    check: Callable[[], tuple[bool, str]]


def _http_ready_check(url: str, timeout: float) -> tuple[bool, str]:
    """请求上游 /healthz，上游返回 2xx 视为依赖可用。"""
    health_url = f"{url.rstrip('/')}/healthz"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as response:
            ok = 200 <= response.status < 300
            return ok, f"HTTP {response.status}"
    except Exception as exc:  # 只记录异常类型，避免把 URL/堆栈写入 readiness 响应。
        return False, type(exc).__name__


def dependency_checks_from_env(
    env_name: str = "RELEASEGUARD_DEPENDENCY_URLS",
    timeout: float = 2.0,
) -> list[ReadinessCheck]:
    """从逗号分隔的环境变量读取上游基础地址并生成依赖检查。"""
    raw = os.getenv(env_name, "")
    urls = [item.strip() for item in raw.split(",") if item.strip()]
    checks: list[ReadinessCheck] = []
    for index, url in enumerate(urls, start=1):
        checks.append(
            ReadinessCheck(
                name=f"dependency_{index}",
                check=lambda u=url, t=timeout: _http_ready_check(u, t),
            )
        )
    return checks
