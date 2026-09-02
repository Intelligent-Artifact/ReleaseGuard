# ReleaseGuard

ReleaseGuard 是一个由 AI 辅助的发布风险分析与策略门控处置平台。它会关联部署变更、指标、日志、链路和 Git 元数据，提出安全的处置建议，并在执行后验证系统是否真正恢复。

## 项目目标

- 检测 canary 发布引入的系统回归。
- 生成以证据为依据的根因结论。
- 将所有基础设施变更限制在受控的 Ops Gateway 之后。
- 对风险动作执行确定性策略检查，并在必要时要求人工批准。
- 重放事故并评估 RCA 准确率、处置质量、安全性、诊断耗时和 MTTR。

## 职责归属

| 区域 | 负责人 | 职责 |
|---|---|---|
| `agent/` | [@Manticore0918](https://github.com/Manticore0918) | Agent Engine、证据、发布关联、策略、HITL、评测和报告 |
| `platform/` | [@adminxue](https://github.com/adminxue) | Demo 服务、Docker/Kubernetes、GitOps、可观测性、Ops Gateway、故障注入和恢复验证 |
| `contracts/` | 双方 | 版本化的 Agent–Gateway API 契约和示例 |
| `scenarios/` | 双方 | 事故定义、预期证据、安全动作和恢复标准 |
| `tests/e2e/` | 双方 | 发布、事故、处置和恢复的端到端测试 |
| `docs/` | 双方 | 架构、决策、运行手册和项目文档 |

## 仓库结构

```text
.
├── agent/                 # AI / Agent 应用
├── platform/              # 运行与可靠性平台
├── contracts/             # OpenAPI、Schema 和测试夹具
├── scenarios/             # 可重复的事故场景
├── tests/e2e/             # 跨边界端到端测试
├── docs/                  # 详细工程手册与路线图
└── .github/               # 协作模板与所有权配置
```

## 当前阶段

**阶段 0：契约与本地平台骨架**

初始共同交付物：

1. 冻结第一版 Agent–Gateway API。
2. 基于契约测试夹具建立 Agent 服务骨架。
3. 建立 Docker Compose 平台和 Demo 服务骨架。
4. 完成一个 slow SQL 发布回归场景的完整闭环。
5. 重复运行同一场景，并记录成功和失败结果。

## 项目文档

- [项目方向与阶段性 Checkpoint](docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md)
- [Agent / AI 工程负责人执行手册](docs/AGENT_ENGINEER_PLAYBOOK.md)
- [DevOps / Platform 工程负责人执行手册](docs/DEVOPS_PLATFORM_PLAYBOOK.md)
- [贡献与协作流程](CONTRIBUTING.md)
- [API 契约说明](contracts/README.md)
- [事故场景说明](scenarios/README.md)

## 工程原则

> AI 提出建议，策略作出裁决，高风险动作由人批准，基础设施负责独立验证。

## 当前状态

仓库当前已包含协作骨架、职责文档、项目路线图和第一版 API 契约。应用代码和可部署基础设施将通过双方 Review 的 Pull Request 逐步加入。
