"""将调查状态渲染为区分事实、推断与建议的中文报告。"""

from __future__ import annotations

from typing import Any


def render_report(state: dict[str, Any]) -> str:
    """生成可审计的 Markdown 事故报告。"""
    evidence = state.get("evidence", [])
    finding = state.get("finding")
    proposal = state.get("proposal")
    lines = [
        f"# ReleaseGuard 调查报告：{state['investigation_id']}",
        "",
        "## 摘要",
        "",
        f"- 状态：`{state['status']}`",
        f"- 环境：`{state['environment']}`",
        f"- 服务：`{state['service']}`",
        f"- 症状：{state['symptom']}",
        "",
        "## 事实",
        "",
    ]
    if evidence:
        lines.extend(f"- `{item['evidence_id']}`：{item['summary']}" for item in evidence)
    else:
        lines.append("- 尚未取得可用证据。")
    lines.extend(["", "## 推断", ""])
    if finding:
        lines.extend(
            [
                f"- 根因判断：{finding['root_cause']}",
                f"- 置信度：{finding['confidence']:.2f}",
                f"- 证据引用：{', '.join(finding['evidence_ids'])}",
            ]
        )
        for limitation in finding.get("limitations", []):
            lines.append(f"- 限制：{limitation}")
    else:
        lines.append("- 当前证据不足，未形成根因判断。")
    lines.extend(["", "## 建议", ""])
    if proposal:
        lines.extend(
            [
                f"- 动作：`{proposal['action']}`",
                f"- 风险：`{proposal['risk']}`",
                f"- 原因：{proposal['reason']}",
                f"- 命中策略：{', '.join(proposal['policy_rule_ids'])}",
            ]
        )
    else:
        lines.append("- `HOLD`：保持现状并补充证据。")
    if state.get("action"):
        lines.extend(
            [
                "",
                "## 执行与恢复验证",
                "",
                f"- Action ID：`{state['action']['action_id']}`",
                f"- Gateway 状态：`{state['action']['status']}`",
                f"- 审计引用：`{state['action']['audit_ref']}`",
            ]
        )
    return "\n".join(lines) + "\n"
