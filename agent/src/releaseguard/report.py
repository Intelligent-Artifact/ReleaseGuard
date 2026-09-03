"""将 IncidentReport 渲染为机器可读 JSON 与人可读 Markdown。

报告必须清楚区分：事实（evidence）、推断（finding）、缺失证据（missing_evidence）
与建议（proposal / decision.note）。这不是美观问题，而是可审计性问题——
读报告的人必须能分辨“Agent 看到了什么”与“Agent 推测了什么”。
"""

from __future__ import annotations

import json
from pathlib import Path

from releaseguard.domain import EVIDENCE_ORDER, EvidenceType, IncidentReport


def to_json(report: IncidentReport) -> str:
    """结构化 JSON：供平台 / eval 直接消费。"""
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def _sort_evidence(report: IncidentReport):
    """按来源类型稳定排序，保证重复渲染顺序一致。"""
    return sorted(report.evidence, key=lambda item: EVIDENCE_ORDER.get(item.type, 99))


def render_markdown(report: IncidentReport) -> str:
    """渲染人可读的中文事故报告，严格区分事实/推断/建议。"""
    inv = report.investigation
    lines: list[str] = [
        f"# ReleaseGuard 契约冒烟调查报告：{inv.investigation_id}",
        "",
        "## 摘要",
        "",
        f"- 调查状态：`{inv.status.value}`",
        f"- 处置建议：`{report.decision.value}`",
        f"- 环境：`{inv.environment}`",
        f"- 服务：`{inv.service}`",
        f"- baseline：`{inv.baseline_version}` / candidate：`{inv.candidate_version}`",
        f"- 症状：{inv.symptom}",
        f"- 报告生成时间：{report.generated_at.isoformat()}",
        "",
        "## 事实（结构化证据）",
        "",
    ]

    evidence = _sort_evidence(report)
    if evidence:
        for item in evidence:
            q = item.quality
            lines.append(
                f"- `{item.evidence_id}`"
                f" · 类型={item.type.value} · 来源=`{item.source}`\n"
                f"  - {item.summary}\n"
                f"  - 版本={item.version or '-'}"
                f" · quality(fresh={q.fresh},complete={q.complete},comparable={q.comparable})"
                f" · refs={item.refs or '-'}"
            )
    else:
        lines.append("- 尚未取得可用证据。")

    lines.extend(["", "## 推断（根因判断）", ""])
    if report.finding:
        finding = report.finding
        lines.append(f"- 主要假设：{finding.root_cause}")
        lines.append(f"- 置信度：{finding.confidence:.2f}")
        lines.append(f"- 引用证据：{', '.join(finding.evidence_ids)}")
        if finding.alternative_hypotheses:
            lines.append("- 替代假设：")
            for alt in finding.alternative_hypotheses:
                note = f"（{alt.note}）" if alt.note else ""
                lines.append(
                    f"  - {alt.hypothesis} · 置信度 {alt.confidence:.2f} {note}"
                )
        if finding.limitations:
            lines.append("- 局限：")
            lines.extend(f"  - {lim}" for lim in finding.limitations)
    else:
        lines.append("- 证据不足，未形成根因判断。")

    lines.extend(["", "## 缺失证据", ""])
    missing = (
        report.finding.missing_evidence
        if report.finding is not None
        else []
    )
    lines.append(
        "、".join(missing) if missing else "无（或本次调查不适用）。"
    )

    lines.extend(["", "## 建议", ""])
    if report.proposal is not None:
        proposal = report.proposal
        target = proposal.target
        lines.append(
            f"- 动作：`{proposal.action.value}`"
            f" · 风险 `{proposal.risk.value}`"
            f" · 需审批={proposal.requires_approval}"
        )
        lines.append(
            f"- 目标：`{target.environment}` / `{target.service}` / "
            f"`{target.from_version}` -> `{target.to_version}`"
        )
        lines.append(f"- 原因：{proposal.reason}")
        lines.append(f"- 引用证据：{', '.join(proposal.evidence_ids)}")
        if proposal.expires_at is not None:
            lines.append(f"- 有效期至：{proposal.expires_at.isoformat()}")
        if report.note:
            lines.append(f"- 说明：{report.note}")
    else:
        lines.append(f"- `{report.decision.value}`：{report.note or '无建议'}")

    return "\n".join(lines) + "\n"


def write_report(report: IncidentReport, output_dir: Path) -> tuple[Path, Path]:
    """把报告写入 output_dir，返回 (json 路径, markdown 路径)。

    output_dir 默认指向 gitignore 的 reports/local/agent，本地复现不会污染仓库。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir / f"incident-{report.investigation.investigation_id}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(to_json(report), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
