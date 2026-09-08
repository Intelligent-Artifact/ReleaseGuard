# ReleaseGuard

ReleaseGuard 是一个**监控驱动的服务故障调查与受控处置系统**。它接收运行告警，通过 Ops Gateway 关联指标、日志、依赖和平台状态，生成有证据的根因结论及建议，并独立验证恢复。

业务应用计划以外部、版本锁定的运行依赖方式集成 [Google Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo)。ReleaseGuard 保持为独立主仓库；默认直接使用经验证的上游发布镜像与清单，并在本仓库维护 Kustomize overlay，不复制完整上游源码，也不以 Online Boutique fork 替代本仓库。上游提供电商业务与流量生成器；本项目的原创成果是集成、监控与告警、调查 Agent、证据契约、恢复验证和可复现评测。

## 交付方向

**先完成作品集展示，再增加面试技术深度。** 首版围绕没有新版本发布的 Redis 依赖故障，展示以下真实链路：

```text
购物车业务异常 → 真实告警 → 自动创建调查 → Gateway 多源取证
             → 根因与人工建议 → 人工恢复 → 独立验证 → 事故报告与评测
```

发布与 Git 变更是可选证据，版本比较保留为后续专项。普通事故不要求 baseline/candidate。

## 当前状态与快速开始

**监控主线目前处于计划迁移阶段，尚未达到首版验收。** 仓库已有发布回归 fixture、Agent smoke、LangGraph 最小调查 harness、自研服务原型和 CP0 HTTP Mock Gateway。当前 harness 使用 fixture 与确定性模型替身，尚未完成新的监控事件、真实 HTTP 取证与真实模型闭环。

现有可运行入口：

- [Agent 安装、harness 与 smoke](agent/README.md)
- [CP0 HTTP Mock Gateway 冒烟](platform/gateway/README.md)
- [历史自研应用的运行说明](platform/apps/README.md)

Online Boutique 部署、监控查询 API、实时告警、现场演示命令、录屏和量化结果均待后续实现。当前不宣称自动修复或生产可用，也不以 Mock 的动作状态作为真实恢复证据。

## 版本路线

| 阶段 | 主要目标 | 展示成果 |
|---|---|---|
| v0.1：监控调查作品集 | 最小真实 Kubernetes 业务与监控，Agent 只读调查 | 告警、证据、人工恢复、独立验证、报告与录屏 |
| v0.2：调查可靠性 | traces、状态恢复、告警关联、至少 5 个实际故障 | 规则/LLM 对照、失败实验、质量和成本数据 |
| v0.3：受控执行 | 一种已审批的无状态服务副本数恢复动作 | 审批、幂等、审计、并发和崩溃实验 |
| v1.0：平台工程深化 | GitOps、CI/CD、漂移处理与发布回归专项 | 面试技术附录、可追溯制品与平台实验 |

首版恢复由独立操作者按运行手册完成，Agent 没有写权限。自动执行属于 v0.3 的验收内容，不能提前计入成果。每一版都同步交付展示材料与双方贡献记录。

## 职责归属

| 区域 | 负责人 | 职责 |
|---|---|---|
| `agent/` | [@Manticore0918](https://github.com/Manticore0918) | 事件消费、调查引擎、多源证据、模型、报告与外部评测 |
| `platform/` | [@adminxue](https://github.com/adminxue) | 上游集成、监控告警、Gateway、故障注入、恢复验证及后续执行 |
| `contracts/` | 双方 | 事件、查询、证据、恢复和后续动作的版本化契约 |
| `scenarios/` | 双方 | 可重复故障、ground truth、清理与恢复标准 |
| `tests/e2e/` | 双方 | 自动告警到调查、恢复验证的跨边界测试 |
| `docs/` | 双方 | 路线图、playbook、ADR、展示与验收要求 |

## 工程原则

- 监控规则发现症状，Agent 验证根因假设；数值、范围和权限由程序校验。
- Agent 只经受限 Gateway 取证，不持有基础设施凭据，不读取场景答案。
- 无数据不等于正常；人工操作成功、告警 resolved 或动作成功不等于业务恢复。
- fixture/live、替身/真实模型、人工/TTL/自动执行分别标注，量化结果保留全部运行记录。
- 上游应用与本项目贡献明确归属，自研业务原型保留但停止扩展。
- G0 同时锁定上游 release、commit、镜像 digest、清单来源和许可证；只有证明确需修改业务源码时才建立独立 fork，且 fork 仍只是 ReleaseGuard 的运行依赖。

## 项目文档

- [项目方向与版本路线图](docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md)
- [Agent / AI 工程负责人执行手册](docs/AGENT_ENGINEER_PLAYBOOK.md)
- [DevOps / Platform 工程负责人执行手册](docs/DEVOPS_PLATFORM_PLAYBOOK.md)
- [方向调整 ADR](docs/adr/001-monitoring-first-online-boutique.md)
- [监控契约迁移计划](contracts/MONITORING_CONTRACT_PLAN.md)
- [API 契约说明](contracts/README.md)
- [事故场景说明](scenarios/README.md)
- [贡献与协作流程](CONTRIBUTING.md)

下一步是 G0：验证并锁定 Online Boutique 版本、资源与 Redis 故障信号，提交可从干净 clone 重建的上游锁定清单与 overlay，并完成是否需要独立 fork 的书面判断；随后冻结监控契约，完成 G1–G3 的真实告警、调查、恢复和作品集验收。
