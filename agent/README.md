# Agent

主要负责人：[@Manticore0918](https://github.com/Manticore0918)

本目录用于存放 ReleaseGuard Agent 应用，包括：

- 调查状态机；
- Ops Gateway 工具客户端；
- 部署与遥测关联；
- 结构化证据和根因结论；
- 确定性风险策略和人工审批生命周期；
- 恢复评估和事故报告；
- 事故重放运行器和评测指标。

## 边界

在生产式流程中，Agent 不得直接调用 Kubernetes、Docker、Argo、Prometheus 或 Loki。它只能通过 Ops Gateway 使用 `../contracts/openapi.yaml` 中定义的版本化契约。

Agent 可以提出动作建议；平台负责独立校验策略、审批、目标状态、幂等性、执行结果和恢复状态。

## 初始任务

1. 定义 Investigation、Evidence、Finding 和 ActionProposal 模型。
2. 实现内存版调查状态机。
3. 根据契约测试夹具生成 Markdown 事故报告。
4. 基于 mock 契约实现部署与指标客户端。
5. 增加确定性风险分类和审批状态。
6. 跑通 slow SQL 端到端场景。

完整计划参见 [Agent 工程负责人执行手册](../docs/AGENT_ENGINEER_PLAYBOOK.md)。
