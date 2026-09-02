"""CP0 契约冒烟测试：确定性 mock 调查 + 可复现输出（CLI / 库函数）。

演示的正是 CP0 与执行手册“阶段 0”的完成标准：

    Agent 在没有真实基础设施时，也能读取共享契约 fixture，
    完成一次模拟调查（fixture → evidence → finding → 报告），
    并输出“测试夹具 → Finding → 报告”的验收证据。

关键取舍：

- 完全确定性：不调用 LLM，不引入随机性。结论由 fixture 数据与固定规则推出，
  因此任意干净环境重复运行都应得到一致结果（CP0 可复现性门禁）。
- 证据 grounded：只引用来自 fixture 的 evidence ID；缺失的日志/trace/git 证据
  会被显式记录在 finding.missing_evidence，绝不编造“已定位到具体 SQL”。
- 保守处置：变更证据（git）缺失时输出 HOLD/INCONCLUSIVE，不直接建议回滚；
  只有当部署+指标+变更三类证据齐备时，才构造 ROLLBACK_RELEASE 建议（仍需审批）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from releaseguard import __version__
from releaseguard.contracts import (
    FixtureBundle,
    RolloutStatus,
    find_repo_root,
    fixture_checklines,
    load_shared_fixtures,
)
from releaseguard.domain import (
    MIN_SAMPLE_COUNT,
    REGRESSION_RATIO,
    ROLLBACK_REQUIRED_TYPES,
    ActionKind,
    ActionProposal,
    ActionTarget,
    AlternativeHypothesis,
    Disposition,
    Evidence,
    EvidenceQuality,
    EvidenceType,
    Finding,
    IncidentReport,
    Investigation,
    InvestigationStatus,
    RiskLevel,
)
from releaseguard.report import write_report

# 冒烟场景的固定上下文：保持确定性，便于重复运行与对照。
SMOKE_INVESTIGATION_ID = "inv_cp0_demo_001"
SMOKE_SYMPTOM = "candidate 的 p95 延迟显著高于 baseline，疑似发布回归"
SMOKE_ENVIRONMENT = "demo"


# ---------------------------------------------------------------------------
# 契约对象 → 结构化证据
# ---------------------------------------------------------------------------


def build_investigation(bundle: FixtureBundle) -> Investigation:
    """根据部署/指标 fixture 建立调查上下文（baseline / candidate / 时间窗）。"""
    deployment = bundle.deployment
    assert deployment is not None, "缺少部署 fixture，无法建立调查上下文"

    current = deployment.current
    previous = deployment.previous
    # 调查起点：最后一次观测时间（指标生成时间），否则用部署元数据时间。
    started_at = (
        bundle.metrics.generated_at if bundle.metrics is not None else current.deployed_at
    )
    return Investigation(
        investigation_id=SMOKE_INVESTIGATION_ID,
        environment=deployment.environment,
        service=deployment.service,
        baseline_version=previous.version if previous else "unknown-baseline",
        candidate_version=current.version,
        deployment_id=deployment.source_refs[0] if deployment.source_refs else None,
        started_at=started_at,
        symptom=SMOKE_SYMPTOM,
    )


def evidence_from_deployment(bundle: FixtureBundle) -> list[Evidence]:
    """把部署响应转换为一条结构化部署证据。"""
    deployment = bundle.deployment
    assert deployment is not None
    current = deployment.current
    previous = deployment.previous

    parts = [
        f"candidate {current.version}（commit {current.commit_sha}）"
        f"于 {current.deployed_at.isoformat()} 上线"
    ]
    if previous:
        parts.append(f"previous={previous.version}（commit {previous.commit_sha}）")
    parts.append(
        f"rollout={deployment.rollout.status.value} / "
        f"candidate_weight={deployment.rollout.candidate_weight}%"
    )
    return [
        Evidence(
            evidence_id=(
                f"deployment:{deployment.service}:{current.version}:{current.commit_sha}"
            ),
            type=EvidenceType.DEPLOYMENT,
            source="ops-gateway:/api/v1/deployments/{service}",
            service=deployment.service,
            version=current.version,
            observed_at=deployment.generated_at,
            summary="；".join(parts) + "。",
            refs=list(deployment.source_refs),
        )
    ]


def evidence_from_metrics(
    bundle: FixtureBundle,
) -> tuple[list[Evidence], list[str]]:
    """把指标比较响应转换为证据，并返回判定为“回归”的指标名。

    只有 comparable 且样本量足够的指标才可能被判定为回归；
    不可比较/无数据会被如实记录，不会被当作正常。
    """
    metrics = bundle.metrics
    if metrics is None:
        return [], []

    evidence: list[Evidence] = []
    regressed: list[str] = []
    for item in metrics.metrics:
        baseline = item.baseline_value
        ratio = item.candidate_value / baseline if baseline else 0.0
        # 可判定回归的两个前提：契约允许比较（comparable）且样本量足够。
        comparable = item.comparable and item.sample_count >= MIN_SAMPLE_COUNT
        is_regression = comparable and item.candidate_value > baseline * REGRESSION_RATIO

        evidence.append(
            Evidence(
                evidence_id=(
                    f"metric:{item.name.value}:{metrics.candidate}:"
                    f"{metrics.generated_at:%H%M%S}"
                ),
                type=EvidenceType.METRIC,
                source="ops-gateway:/api/v1/metrics/compare",
                service=metrics.service,
                version=metrics.candidate,
                observed_at=metrics.generated_at,
                # 契约声明不可比的数据，质量标记也要如实反映，不能当作正常。
                quality=EvidenceQuality(comparable=item.comparable),
                summary=(
                    f"{item.name.value}：candidate={item.candidate_value}{item.unit} "
                    f"vs baseline={item.baseline_value}{item.unit}"
                    f"（约 {ratio:.2f} 倍；样本 {item.sample_count}；"
                    f"comparable={item.comparable}）"
                )
                + "。",
                value=item.candidate_value,
                unit=item.unit,
                refs=list(metrics.source_refs),
            )
        )
        if is_regression:
            regressed.append(item.name.value)
    return evidence, regressed


# ---------------------------------------------------------------------------
# finding 与确定性裁决
# ---------------------------------------------------------------------------


def build_finding(
    investigation: Investigation,
    evidence: list[Evidence],
    regressed_metrics: list[str],
    bundle: FixtureBundle,
) -> Finding | None:
    """基于证据与回归判定形成带限制的根因判断；证据不足时返回 None。"""
    # 需要部署与至少一个可比较指标，才能形成“候选版本回归”的判断。
    present = {item.type for item in evidence}
    if (
        EvidenceType.DEPLOYMENT not in present
        or EvidenceType.METRIC not in present
        or not regressed_metrics
    ):
        return None

    deployment = bundle.deployment
    assert deployment is not None
    current = deployment.current

    # ---- 确定性置信度组合（冒烟演示用启发式；正式评分由外部 evaluator 负责）----
    confidence = 0.40  # 基础分：已确认 candidate 方向回归。
    if "p95_latency" in regressed_metrics:
        confidence += 0.20
    if deployment.rollout.status == RolloutStatus.PROGRESSING and deployment.previous:
        confidence += 0.15
    confidence -= 0.10  # 缺少日志/trace/git，无法定位到具体语句。
    confidence = max(0.0, min(1.0, confidence))

    # 缺失证据清单：显式写出仍需要的来源，不把“无数据”当正常。
    wanted = {"log", "trace", "git"}
    missing_evidence = sorted(wanted - {t.value for t in present})

    regressed_summary = "、".join(regressed_metrics)
    root_cause = (
        f"候选版本 {current.version}（commit {current.commit_sha}）上线后，"
        f"指标 {regressed_summary} 出现仅 candidate 可观测的回归；"
        f"主要假设为 v2 引入的变更导致后端延迟上升"
        f"（方向疑似同步/数据库类查询），但缺少日志与链路证据，"
        f"无法定位到具体 SQL 语句或调用路径。"
    )
    return Finding(
        affected_service=investigation.service,
        root_cause=root_cause,
        confidence=confidence,
        evidence_ids=[item.evidence_id for item in evidence],
        alternative_hypotheses=[
            AlternativeHypothesis(
                hypothesis="与本次发布无关的下游依赖或数据库全局饱和",
                confidence=0.15,
                note="尚未被现有证据排除，需要全局指标或对应日志进一步核对。",
            ),
            AlternativeHypothesis(
                hypothesis="流量倾斜或测量噪声导致的假阳性",
                confidence=0.10,
                note="comparable=true 且样本量足够，但 candidate 权重低，仍需复现确认。",
            ),
        ],
        limitations=[
            "结论基于 deployment + metrics 两类来源，未包含日志、链路与代码变更证据。",
            "未声称定位到具体 SQL：当前证据不足以支撑该粒度结论。",
            "置信度为确定性启发式，用于冒烟演示；正式评分由外部 evaluator 完成。",
        ],
        missing_evidence=missing_evidence,
    )


def build_rollback_proposal(
    investigation: Investigation, finding: Finding
) -> ActionProposal:
    """构造 ROLLBACK_RELEASE 建议（MEDIUM 风险，需要人工审批，不自动执行）。"""
    return ActionProposal(
        proposal_id=f"prop_{investigation.investigation_id}",
        investigation_id=investigation.investigation_id,
        action=ActionKind.ROLLBACK_RELEASE,
        target=ActionTarget(
            environment=investigation.environment,
            service=investigation.service,
            from_version=investigation.candidate_version,
            to_version=investigation.baseline_version,
        ),
        reason=(
            "候选版本出现仅 candidate 可观测的 SLO 回归，部署、指标与代码变更"
            "证据齐备；建议回滚 candidate 到 baseline，由平台独立验证恢复后再决定重试。"
        ),
        evidence_ids=finding.evidence_ids,
        risk=RiskLevel.MEDIUM,
        requires_approval=True,
        expires_at=investigation.started_at + timedelta(minutes=5),
    )


def decide(
    investigation: Investigation,
    evidence: list[Evidence],
    finding: Finding | None,
) -> tuple[Disposition, ActionProposal | None, str]:
    """确定性处置裁决：由规则决定，不由 LLM 自评（docs §11 / §10）。

    输出三条互斥路径：

    1. finding 为空 → INCONCLUSIVE：部署/指标缺失、不可比或未检测到回归，
       不足以形成可执行判断（保持观察，不触发动作）；
    2. 证据覆盖部署+指标+变更（git）且置信度达标 → ROLLBACK_RELEASE 建议，
       但必须人工审批，Agent 不自动执行；
    3. 其余（确认了 candidate 回归但缺变更证据）→ HOLD，补充证据后再决策。

    返回 (处置结论, 可执行建议, 说明文案)。
    """
    if finding is None:
        return (
            Disposition.INCONCLUSIVE,
            None,
            "未形成可执行的根因判断（部署/指标缺失、不可比或未检测到回归）；"
            "保持观察，不触发任何执行动作。",
        )

    present = {item.type for item in evidence}
    if ROLLBACK_REQUIRED_TYPES.issubset(present) and finding.confidence >= 0.6:
        return (
            Disposition.ROLLBACK_RELEASE,
            build_rollback_proposal(investigation, finding),
            "部署+指标+代码变更三类证据齐备，按 grounding 规则建议回滚；"
            "正式执行仍需人工审批并由平台独立验证。",
        )
    return (
        Disposition.HOLD,
        None,
        "已确认 candidate 方向回归，但缺少代码变更（git）证据，"
        "暂不直接建议回滚；建议补齐日志/trace/git 证据后再决策。",
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _generated_at(bundle: FixtureBundle):
    """报告生成时间取最后一条 fixture 的观测时间，保证确定性。"""
    if bundle.metrics is not None:
        return bundle.metrics.generated_at
    if bundle.deployment is not None:
        return bundle.deployment.generated_at
    return None


def run_smoke(bundle: FixtureBundle) -> IncidentReport:
    """执行一次确定性 mock 调查，返回事故报告。"""
    if bundle.deployment is None or bundle.metrics is None:
        return _inconclusive_report(bundle)

    investigation = build_investigation(bundle)
    evidence = evidence_from_deployment(bundle)
    metric_evidence, regressed = evidence_from_metrics(bundle)
    evidence.extend(metric_evidence)

    finding = build_finding(investigation, evidence, regressed, bundle)
    decision, proposal, message = decide(investigation, evidence, finding)
    status = (
        InvestigationStatus.INCONCLUSIVE
        if decision == Disposition.INCONCLUSIVE
        else InvestigationStatus.DIAGNOSED
    )
    return IncidentReport(
        schema_version=__version__,
        generated_at=_generated_at(bundle) or investigation.started_at,
        investigation=investigation.model_copy(update={"status": status}),
        decision=decision,
        evidence=evidence,
        finding=finding,
        proposal=proposal,
        note=message,
    )


def _inconclusive_report(bundle: FixtureBundle) -> IncidentReport:
    """数据缺失时的降级报告：输出 INCONCLUSIVE，绝不编造结论。"""
    if bundle.deployment is not None:
        investigation = build_investigation(bundle)
        evidence = evidence_from_deployment(bundle)
        metric_evidence, _ = evidence_from_metrics(bundle)
        evidence.extend(metric_evidence)
    else:
        investigation = Investigation(
            investigation_id=SMOKE_INVESTIGATION_ID,
            environment=SMOKE_ENVIRONMENT,
            service="payment-service",
            baseline_version="unknown-baseline",
            candidate_version="unknown-candidate",
            started_at=datetime.now(timezone.utc),
            symptom=SMOKE_SYMPTOM,
        )
        evidence = []

    note = "部署或指标数据缺失，无法完成 baseline/candidate 比较。"
    if bundle.errors:
        note += " " + "；".join(bundle.errors)
    return IncidentReport(
        schema_version=__version__,
        generated_at=_generated_at(bundle) or investigation.started_at,
        investigation=investigation.model_copy(
            update={"status": InvestigationStatus.INCONCLUSIVE}
        ),
        decision=Disposition.INCONCLUSIVE,
        evidence=evidence,
        finding=None,
        proposal=None,
        note=note,
    )


def default_output_dir() -> Path:
    """默认输出目录：仓库根 reports/local/agent（已被 .gitignore 忽略）。"""
    return find_repo_root() / "reports" / "local" / "agent"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：加载共享 fixture → mock 调查 → 打印并保存报告。

    stdout 即为可复现的“Agent 契约冒烟测试输出”，可作为 CP0 验收证据留档：
        在命令后追加 `> agent-smoke-output.txt` 即可保存。
    """
    parser = argparse.ArgumentParser(description="ReleaseGuard Agent CP0 契约冒烟测试")
    parser.add_argument("--fixtures-dir", default=None, help="共享契约 fixture 目录")
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help="报告输出目录（默认 reports/local/agent）",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 兼容 Windows 控制台
    except Exception:
        pass

    print("=" * 60)
    print("ReleaseGuard Agent 契约冒烟测试")
    print(f"schema_version={__version__}  模式=mock/fixture（无真实基础设施）")
    print("=" * 60)

    bundle = load_shared_fixtures(args.fixtures_dir)
    print("\n[1/4] 契约 fixture 符合性（contracts/openapi.yaml v0.1）")
    for line in fixture_checklines(bundle):
        print(line)
    if not bundle.ok:
        print("\nFAIL：契约 fixture 校验未通过：")
        for err in bundle.errors:
            print(f"  - {err}")
        return 1
    print("  -> 全部共享 fixture 符合契约。")

    print("\n[2/4] 建立 mock 调查上下文")
    investigation = build_investigation(bundle)
    print(
        f"  investigation={investigation.investigation_id} "
        f"service={investigation.service} "
        f"baseline={investigation.baseline_version} "
        f"candidate={investigation.candidate_version}"
    )
    print(f"  symptom={investigation.symptom}")

    print("\n[3/4] 确定性调查：fixture -> evidence -> finding -> 处置")
    report = run_smoke(bundle)
    for item in report.evidence:
        quality_ok = (
            item.quality.comparable and item.quality.complete and item.quality.fresh
        )
        print(f"  evidence [{item.type.value}] {item.evidence_id} (quality_ok={quality_ok})")
    if report.finding:
        print(
            f"  finding 置信度={report.finding.confidence:.2f} "
            f"证据数={len(report.finding.evidence_ids)}"
        )
        print(f"  missing_evidence={report.finding.missing_evidence or '-'}")
    disposition_line = f"处置 = {report.decision.value}"
    if report.proposal is not None:
        disposition_line += (
            f"（动作 {report.proposal.action.value} / 风险 {report.proposal.risk.value}"
            f" / 需审批={report.proposal.requires_approval}）"
        )
    print(f"  {disposition_line}")

    print("\n[4/4] 生成并保存报告")
    out_dir = Path(args.output_dir)
    json_path, md_path = write_report(report, out_dir)
    print(f"  JSON     -> {json_path}")
    print(f"  Markdown -> {md_path}")

    print("\n" + "=" * 60)
    if report.decision.value in ("INCONCLUSIVE", "HOLD"):
        print(f"PASS：mock 调查完成，处置={report.decision.value}（保守，未触发任何执行动作）")
    else:
        print("PASS：mock 调查完成，处置=ROLLBACK_RELEASE（仅构造建议，未真正提交）")
    print("Agent 契约冒烟测试通过。")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
