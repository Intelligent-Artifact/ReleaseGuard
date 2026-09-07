"""只读数据源接口与开发期间的 fixture 替身。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from releaseguard.contracts import resolve_fixtures_dir
from releaseguard.harness_models import DeploymentQuery, MetricsQuery


class GatewayClient(Protocol):
    """HTTP 实现可替换此接口；返回值统一由 harness 校验。

    适配器必须采用可取消的异步 I/O，不得在事件循环中执行阻塞请求。
    当前接口没有写操作，也不暴露场景标准答案。
    """

    async def get_deployment(self, query: DeploymentQuery) -> dict:
        """获取给定环境和服务的部署信息。"""
        ...

    async def compare_metrics(self, query: MetricsQuery) -> dict:
        """按明确版本和时间窗获取指标。"""
        ...


class FixtureGateway:
    """仅供最小 harness 开发使用，读取两份只读报文，不加载回滚凭据。"""

    def __init__(self, fixtures_dir: Path | str | None = None):
        self.fixtures_dir = resolve_fixtures_dir(fixtures_dir)

    async def _read(self, filename: str) -> dict:
        """固定文件名不由模型提供；响应标签由 harness 再次核对。"""
        raw = await asyncio.to_thread(
            (self.fixtures_dir / filename).read_text, encoding="utf-8"
        )
        return json.loads(raw)

    async def get_deployment(self, query: DeploymentQuery) -> dict:
        """返回部署 fixture；不伪装成实际 HTTP Gateway。"""
        return await self._read("deployment-response.json")

    async def compare_metrics(self, query: MetricsQuery) -> dict:
        """返回固定指标 fixture，不重写其服务、版本或时间窗标签。"""
        return await self._read("metrics-compare-response.json")
