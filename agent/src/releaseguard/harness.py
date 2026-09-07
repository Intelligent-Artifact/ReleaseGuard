"""LangGraph 最小调查：只读工具循环、证据校验、裁决与报告。"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from releaseguard import __version__
from releaseguard.contracts import (
    DeploymentResponse,
    FixtureBundle,
    MetricsCompareResponse,
)
from releaseguard.domain import (
    MIN_SAMPLE_COUNT,
    Disposition,
    Evidence,
    EvidenceType,
    Finding,
    IncidentReport,
    Investigation,
    InvestigationStatus,
)
from releaseguard.gateway import FixtureGateway, GatewayClient
from releaseguard.harness_models import (
    DeploymentQuery,
    DeterministicModel,
    HarnessResult,
    InvestigationRequest,
    MetricsQuery,
    ModelAdapter,
    ModelContext,
    ModelTurn,
    RunEvent,
    RunLimits,
)
from releaseguard.report import write_report
from releaseguard.smoke import (
    UNKNOWN_BASELINE_VERSION,
    UNKNOWN_CANDIDATE_VERSION,
    build_finding,
    build_investigation,
    decide,
    default_output_dir,
    evidence_from_deployment,
    evidence_from_metrics,
)


class InvestigationState(TypedDict, total=False):
    """图内状态；外部输入、工具结果与模型输出使用 Pydantic 显式校验。"""

    request: InvestigationRequest
    investigation: Investigation
    deployment: DeploymentResponse
    metrics: MetricsCompareResponse
    evidence: list[Evidence]
    regressed_ids: list[str]
    draft_finding: Finding | None
    finding: Finding | None
    decision: Disposition
    turn: ModelTurn
    route: Literal["tool", "validate", "report"]
    report: IncidentReport
    events: list[RunEvent]
    model_calls: int
    tool_calls: int
    error: str | None
    note: str


def _events(
    state: InvestigationState, node: str, outcome: str, detail: str = ""
) -> list[RunEvent]:
    """返回新的运行记录，避免在节点之间共享可变列表。"""
    return [*state["events"], RunEvent(node=node, outcome=outcome, detail=detail)]


def _failure(state: InvestigationState, node: str, code: str, note: str) -> dict:
    """失败统一进入报告出口，保留已取得的证据。"""
    return {
        "route": "report",
        "error": code,
        "finding": None,
        "note": note,
        "events": _events(state, node, code, note),
    }


def _collect(state: InvestigationState) -> dict:
    """复用调查种子的转换规则；临时 bundle 仅作参数桥接，不读取文件。

    数据始终来自注入的 GatewayClient。fixture 路径不会传入图状态或模型上下文。
    """
    bundle = FixtureBundle(
        Path("."), deployment=state.get("deployment"), metrics=state.get("metrics")
    )
    investigation = build_investigation(bundle).model_copy(
        update={
            "investigation_id": state["request"].investigation_id,
            "started_at": state["request"].started_at,
            "symptom": state["request"].symptom,
            "status": InvestigationStatus.COLLECTING,
        }
    )
    evidence = evidence_from_deployment(bundle)
    metric_evidence, regressed, regressed_ids = evidence_from_metrics(bundle)
    if bundle.metrics is not None:
        for item, metric in zip(metric_evidence, bundle.metrics.metrics):
            item.quality.comparable = (
                metric.comparable and metric.sample_count >= MIN_SAMPLE_COUNT
            )
    evidence.extend(metric_evidence)
    # 当前种子的倍数规则仅支持“越高越差”的延迟与错误率；不推断其他指标方向。
    supported = {"p95_latency", "error_rate"}
    regressed_ids = [
        eid for name, eid in zip(regressed, regressed_ids) if name in supported
    ]
    regressed = [name for name in regressed if name in supported]
    draft = build_finding(investigation, evidence, regressed, regressed_ids, bundle)
    return {
        "investigation": investigation,
        "evidence": evidence,
        "regressed_ids": regressed_ids,
        "draft_finding": draft,
    }


def _check_finding(state: InvestigationState, finding: Finding) -> None:
    """检查引用是否属于当前调查并支持回归，不能只校验字符串列表形状。"""
    inv = state["investigation"]
    known = {item.evidence_id: item for item in state["evidence"]}
    ids = finding.evidence_ids
    if len(known) != len(state["evidence"]) or len(set(ids)) != len(ids):
        raise ValueError("证据 ID 必须唯一")
    if finding.affected_service != inv.service or any(eid not in known for eid in ids):
        raise ValueError("结论服务不匹配或引用不存在的证据")
    referenced = [known[eid] for eid in ids]
    if len({item.type for item in referenced}) < 2:
        raise ValueError("结论至少引用两种来源")
    if not set(ids).intersection(state["regressed_ids"]):
        raise ValueError("结论必须引用本次可比较的回归指标")
    if not any(item.type == EvidenceType.DEPLOYMENT for item in referenced):
        raise ValueError("结论缺少部署上下文")
    for item in referenced:
        if item.service != inv.service or item.version not in {
            inv.baseline_version,
            inv.candidate_version,
        }:
            raise ValueError("引用证据与调查版本不一致")
        if not (
            item.quality.fresh and item.quality.complete and item.quality.comparable
        ):
            raise ValueError("不能引用质量不满足要求的证据")
        if (
            item.type == EvidenceType.METRIC
            and item.evidence_id not in state["regressed_ids"]
        ):
            raise ValueError("不能用未回归的指标支持回归结论")
    for alternative in finding.alternative_hypotheses:
        if any(eid not in known for eid in alternative.excluded_by):
            raise ValueError("替代假设引用不存在的证据")
    if finding.confidence > 0.8 and not any(
        a.excluded_by for a in finding.alternative_hypotheses
    ):
        raise ValueError("高置信度判断必须提供排除替代假设的证据")


class InvestigationHarness:
    """可复用的已编译图；每次运行的状态独立，不含任何写工具。"""

    def __init__(
        self,
        gateway: GatewayClient,
        model: ModelAdapter | None = None,
        limits: RunLimits | None = None,
    ):
        self.gateway = gateway
        self.model = model if model is not None else DeterministicModel()
        self.limits = limits if limits is not None else RunLimits()
        builder = StateGraph(InvestigationState)
        builder.add_node("model", self._model)
        builder.add_node("tool", self._tool)
        builder.add_node("validate", self._validate)
        builder.add_node("decide", self._decide)
        builder.add_node("report", self._report)
        builder.add_edge(START, "model")
        builder.add_conditional_edges(
            "model",
            lambda state: state["route"],
            {"tool": "tool", "validate": "validate", "report": "report"},
        )
        builder.add_conditional_edges(
            "tool",
            lambda state: "report" if state["error"] else "model",
            {"model": "model", "report": "report"},
        )
        builder.add_conditional_edges(
            "validate",
            lambda state: "report" if state["error"] else "decide",
            {"decide": "decide", "report": "report"},
        )
        builder.add_edge("decide", "report")
        builder.add_edge("report", END)
        self.graph = builder.compile()

    async def _model(self, state: InvestigationState) -> dict:
        """模型只能看到深拷贝快照，输出再次校验，不能直接改图状态。"""
        if state["model_calls"] >= self.limits.max_model_calls:
            return _failure(state, "model", "BUDGET_EXHAUSTED", "模型调用次数达到上限")
        context = ModelContext(
            request=state["request"],
            investigation=state["investigation"],
            deployment=state.get("deployment"),
            metrics=state.get("metrics"),
            evidence=state["evidence"],
            draft_finding=state.get("draft_finding"),
        ).model_copy(deep=True)
        count = {"model_calls": state["model_calls"] + 1}
        try:
            result = await asyncio.wait_for(
                self.model.next_turn(context), self.limits.call_timeout_seconds
            )
            turn = ModelTurn.model_validate(
                result.model_dump() if isinstance(result, ModelTurn) else result
            )
        except TimeoutError:
            return {
                **count,
                **_failure(state, "model", "MODEL_TIMEOUT", "模型调用超时"),
            }
        except ValidationError:
            return {
                **count,
                **_failure(
                    state, "model", "INVALID_MODEL_OUTPUT", "模型输出或工具名不符合约定"
                ),
            }
        except Exception:
            return {
                **count,
                **_failure(state, "model", "MODEL_ERROR", "模型适配器失败"),
            }
        return {
            **count,
            "turn": turn,
            "route": "tool" if turn.kind == "tool" else "validate",
            "events": _events(state, "model", turn.kind),
        }

    async def _tool(self, state: InvestigationState) -> dict:
        """先检查工具参数与目标，再调用数据源并验证返回报文。"""
        if state["tool_calls"] >= self.limits.max_tool_calls:
            return _failure(state, "tool", "BUDGET_EXHAUSTED", "工具调用次数达到上限")
        call = state["turn"].tool_call
        assert call is not None
        request = state["request"]
        try:
            query_type = (
                DeploymentQuery if call.name == "get_deployment" else MetricsQuery
            )
            query = query_type.model_validate(call.arguments)
            if (query.environment, query.service) != (
                request.environment,
                request.service,
            ):
                raise ValueError("工具目标不能超出调查范围")
            if isinstance(query, MetricsQuery):
                deployment = state.get("deployment")
                if deployment is None or deployment.previous is None:
                    raise ValueError("尚未获得明确的新旧版本")
                if (query.baseline, query.candidate, query.window) != (
                    deployment.previous.version,
                    deployment.current.version,
                    request.window,
                ) or query.baseline == query.candidate:
                    raise ValueError("指标参数与调查版本或时间窗不一致")
        except ValueError:
            return _failure(
                state, "tool", "INVALID_TOOL_CALL", "工具参数不合法或超出调查范围"
            )
        count = {"tool_calls": state["tool_calls"] + 1}
        try:
            if call.name == "get_deployment":
                raw = await asyncio.wait_for(
                    self.gateway.get_deployment(query), self.limits.call_timeout_seconds
                )
                response = DeploymentResponse.model_validate(raw)
                updates = {"deployment": response}
            else:
                raw = await asyncio.wait_for(
                    self.gateway.compare_metrics(query),
                    self.limits.call_timeout_seconds,
                )
                response = MetricsCompareResponse.model_validate(raw)
                updates = {"metrics": response}
        except TimeoutError:
            return {
                **count,
                **_failure(state, "tool", "TOOL_TIMEOUT", f"{call.name} 超时"),
            }
        except FileNotFoundError:
            return {
                **count,
                **_failure(state, "tool", "DATA_UNAVAILABLE", f"{call.name} 数据缺失"),
            }
        except (ValidationError, ValueError):
            return {
                **count,
                **_failure(
                    state, "tool", "INVALID_RESPONSE", f"{call.name} 返回无效报文"
                ),
            }
        except Exception:
            return {
                **count,
                **_failure(state, "tool", "TOOL_ERROR", f"{call.name} 数据源调用失败"),
            }
        if (response.environment, response.service) != (
            request.environment,
            request.service,
        ):
            return {
                **count,
                **_failure(
                    state, "tool", "CONTEXT_MISMATCH", "响应环境或服务与调查不一致"
                ),
            }
        if isinstance(response, MetricsCompareResponse) and (
            response.baseline,
            response.candidate,
            response.window,
        ) != (query.baseline, query.candidate, query.window):
            return {
                **count,
                **_failure(
                    state, "tool", "CONTEXT_MISMATCH", "指标响应版本或时间窗不匹配"
                ),
            }
        # 部署重复查询可能代表新发布；已收集指标不能与变化后的部署继续拼接。
        if (
            isinstance(response, DeploymentResponse)
            and state.get("deployment") is not None
        ):
            if response != state["deployment"]:
                return {
                    **count,
                    **_failure(
                        state, "tool", "CONTEXT_MISMATCH", "调查期间部署上下文发生变化"
                    ),
                }
        collected = _collect({**state, **updates})
        return {
            **count,
            **updates,
            **collected,
            "events": _events(state, "tool", "OK", call.name),
        }

    def _validate(self, state: InvestigationState) -> dict:
        """不允许模型绕过证据校验直接形成处置建议。"""
        finding = state["turn"].finding
        if finding is not None:
            try:
                _check_finding(state, finding)
            except ValueError as exc:
                return _failure(state, "validate", "INVALID_FINDING", str(exc))
        return {"finding": finding, "events": _events(state, "validate", "OK")}

    def _decide(self, state: InvestigationState) -> dict:
        """沿用确定性裁决，只传入已校验且被结论引用的证据。"""
        finding = state.get("finding")
        ids = set(finding.evidence_ids) if finding else set()
        decision, _, note = decide(
            state["investigation"],
            [e for e in state["evidence"] if e.evidence_id in ids],
            finding,
        )
        if decision not in {Disposition.HOLD, Disposition.INCONCLUSIVE}:
            decision, note = (
                Disposition.HOLD,
                "当前 harness 只允许只读调查，尚未接入动作流程。",
            )
        return {
            "decision": decision,
            "note": note,
            "events": _events(state, "decide", decision.value),
        }

    def _report(self, state: InvestigationState) -> dict:
        """统一收束成功和失败路径；当前只读范围不会生成可执行提案。"""
        finding = state.get("finding") if not state["error"] else None
        decision = state.get("decision", Disposition.INCONCLUSIVE)
        status = (
            InvestigationStatus.DIAGNOSED
            if finding is not None
            else InvestigationStatus.INCONCLUSIVE
        )
        timestamps = [item.observed_at for item in state["evidence"]]
        report = IncidentReport(
            schema_version=__version__,
            generated_at=max(timestamps) if timestamps else state["request"].started_at,
            investigation=state["investigation"].model_copy(update={"status": status}),
            decision=decision,
            evidence=state["evidence"],
            finding=finding,
            note=state.get("note", "未获得足够证据，停止调查。"),
        )
        return {"report": report, "events": _events(state, "report", decision.value)}

    async def run(self, request: InvestigationRequest) -> HarnessResult:
        """每次调用建立独立状态，失败报告同样包含次数和执行记录。"""
        request = InvestigationRequest.model_validate(request.model_dump())
        investigation = Investigation(
            investigation_id=request.investigation_id,
            environment=request.environment,
            service=request.service,
            baseline_version=UNKNOWN_BASELINE_VERSION,
            candidate_version=UNKNOWN_CANDIDATE_VERSION,
            started_at=request.started_at,
            symptom=request.symptom,
            status=InvestigationStatus.COLLECTING,
        )
        final = await self.graph.ainvoke(
            {
                "request": request,
                "investigation": investigation,
                "evidence": [],
                "regressed_ids": [],
                "finding": None,
                "events": [],
                "model_calls": 0,
                "tool_calls": 0,
                "error": None,
            },
            config={"recursion_limit": 2 * self.limits.max_model_calls + 6},
        )
        return HarnessResult(
            report=final["report"],
            events=final["events"],
            model_calls=final["model_calls"],
            tool_calls=final["tool_calls"],
            error=final["error"],
        )


def main(argv: list[str] | None = None) -> int:
    """离线 CLI：保存事故报告和包含工具轨迹的运行记录。"""
    parser = argparse.ArgumentParser(
        description="ReleaseGuard 最小调查 harness（LangGraph + fixture）"
    )
    parser.add_argument("--fixtures-dir", help="只读 fixture 所在目录")
    parser.add_argument("--output-dir", help="报告目录，仓库外运行时必须显式指定")
    parser.add_argument("--service", default="payment-service", help="调查服务")
    parser.add_argument(
        "--environment", default="demo", choices=["demo", "staging"], help="调查环境"
    )
    args = parser.parse_args(argv)
    try:
        request = InvestigationRequest(
            service=args.service, environment=args.environment
        )
        output = (
            Path(args.output_dir)
            if args.output_dir
            else default_output_dir() / "harness"
        )
        result = asyncio.run(
            InvestigationHarness(FixtureGateway(args.fixtures_dir)).run(request)
        )
        json_path, md_path = write_report(result.report, output)
        run_path = output / f"run-{request.investigation_id}.json"
        run_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(f"FAIL：无法启动调查或保存报告（{type(exc).__name__}）")
        return 1
    print(f"模式=fixture/确定性替身 处置={result.report.decision.value}")
    print(
        f"模型调用={result.model_calls} 工具调用={result.tool_calls} 错误={result.error or '无'}"
    )
    print(f"JSON：{json_path}\nMarkdown：{md_path}\n运行记录：{run_path}")
    return 1 if result.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
