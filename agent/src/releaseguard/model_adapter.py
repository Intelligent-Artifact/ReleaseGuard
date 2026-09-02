"""LangChain 模型与 tool calling 适配。"""

from __future__ import annotations

import json
from typing import Any, Sequence

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool


class FixtureToolCallingModel(BaseChatModel):
    """离线可运行、遵循 LangChain tool calling 协议的夹具模型。"""

    model_name: str = "fixture-tool-calling"
    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "releaseguard-fixture"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> FixtureToolCallingModel:
        """记录 LangChain 已绑定的工具名称。"""
        names = tuple(
            tool.name if isinstance(tool, BaseTool) else getattr(tool, "__name__", str(tool))
            for tool in tools
        )
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """按部署后指标的固定顺序生成结构化工具调用。"""
        context = self._context(messages)
        called = {message.name for message in messages if isinstance(message, ToolMessage)}
        if "get_deployment" not in called:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_deployment",
                        "args": {
                            "environment": context["environment"],
                            "service": context["service"],
                        },
                        "id": "fixture-call-deployment",
                        "type": "tool_call",
                    }
                ],
            )
        elif "compare_metrics" not in called:
            deployment = self._last_tool_payload(messages, "get_deployment")
            previous = deployment.get("previous") or {}
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "compare_metrics",
                        "args": {
                            "environment": context["environment"],
                            "service": context["service"],
                            "baseline": previous.get("version", "unknown"),
                            "candidate": deployment.get("current", {}).get("version", "unknown"),
                            "window": "5m",
                        },
                        "id": "fixture-call-metrics",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            message = AIMessage(content="只读证据收集已完成，交由确定性关联与策略节点处理。")
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _context(messages: list[BaseMessage]) -> dict[str, Any]:
        """从结构化用户消息中读取调查边界。"""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return json.loads(str(message.content))
        raise ValueError("缺少调查上下文")

    @staticmethod
    def _last_tool_payload(messages: list[BaseMessage], name: str) -> dict[str, Any]:
        """读取指定工具最近一次成功结果。"""
        for message in reversed(messages):
            if isinstance(message, ToolMessage) and message.name == name:
                return json.loads(str(message.content))
        return {}


def build_model(model_name: str) -> BaseChatModel:
    """构建离线夹具模型或 LangChain 支持的生产模型。"""
    if model_name == "fixture":
        return FixtureToolCallingModel()
    return init_chat_model(model_name)

