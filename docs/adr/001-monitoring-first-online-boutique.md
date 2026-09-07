# ADR-001：监控主线、Online Boutique 与作品集优先交付

> 日期：2026-09-08<br>
> 状态：根据本次计划调整确定方向；具体部署与契约仍需按 Gate 验收。<br>
> 负责人：@Manticore0918、@adminxue

## 背景

项目原始意图是监控信号触发 Agent 排查服务故障。仓库早期规划将主线限定为 canary 发布回归，调查模型、metrics compare 和回滚建议都依赖版本差异。这使无发布的依赖故障、运行故障难以自然进入调查。

同时，自研电商服务消耗业务开发时间，难以直接体现两人的 Agent 与运维职责。新的目标是先最大化作品集展示价值，再通过实验证据补足面试中的技术深度。

## 决策

1. 将项目定位调整为监控驱动的服务故障调查与受控处置系统，保留 ReleaseGuard 名称。
2. 使用 Google Online Boutique 作为被监控应用，复用上游业务流程、依赖及流量生成器；原创成果集中在集成、监控、调查、验证与评测。
3. 首版覆盖无新发布的购物车至 Redis 故障链路，部署必要业务依赖，但不承诺所有服务的诊断能力。
4. Kubernetes 最小运行底座提前，首选本地 Kind；GitOps、Argo Rollouts、云平台和完整 traces 延后。
5. v0.1 交付真实告警、只读 Agent、人工恢复和独立验证；v0.2 加强调查可靠性；v0.3 才开放一种经审批的真实写动作；v1.0 增加平台深化与发布专项。
6. 发布上下文作为可选证据，不要求所有事故存在 baseline/candidate。保留旧发布接口与测试，监控契约以新增版本迁移。
7. 每阶段同步交付报告、失败结果、演示和双方贡献证据；首版不宣称自动修复或生产可用。

## 考虑过的方案

| 方案 | 优点 | 未采用为主线的原因 |
|---|---|---|
| 继续开发单服务 slow SQL 发布演示 | 已有原型，比较与回滚清晰 | 仍绑定发布，投入偏向业务代码 |
| 先完成 Mock 自动回滚再接真实环境 | CI 易复现，动作故事完整 | 真实监控与平台贡献推迟，演示容易误读为模拟系统 |
| 首版同时完成所有遥测、自动执行和 GitOps | 技术覆盖广 | 增大首个可展示版本的交付成本 |
| Online Boutique + 最小真实监控调查 | 自带业务流程，双方职责直接可见 | 需要提前验证 Kubernetes 资源与实际遥测缺口；本次采用 |

## 结果与代价

- 不再继续扩展 `platform/apps/` 的业务原型，但保留其代码与运行说明作为历史资产。
- Online Boutique 替代的是被监控业务应用，不替代 ReleaseGuard 的 Gateway、事件入口、Agent 或恢复验证器。
- 平台开发量转向上游版本锁定、数据适配、告警质量、故障清理和可靠运行；不会因为复用应用而自动获得完整可观测性。
- 首版降低自动执行范围，保留人工操作审计与独立验证。自动处置是后续明确 Gate，不能在作品集中提前声明。
- 项目版本与 API 版本分别管理；本次仅调整计划文档，不静默修改现有运行契约。

## 实施前验证与复审条件

G0 必须验证实际上游资源、Redis 场景、业务信号、日志来源和清理行为，锁定具体 release/commit/digest。若资源需求不可接受、故障无法稳定复现或关键证据缺失，记录实验并调整部署/采集方案，不能用想象中的能力通过验收。

首次修改上游业务代码、扩大正式诊断范围、开放新写动作或改变恢复语义时，复审影响并更新本 ADR 或新增 ADR。常规实现按已批准路线自主推进。

## 验收依据

- 无新应用版本发布时，真实告警可以自动触发调查并关联多源证据。
- Agent 不读取答案、不持有基础设施权限；人工操作、TTL 清理和自动执行的结果分别归因。
- 恢复以新的业务窗口与样本判断，操作成功或告警 resolved 均不足以证明恢复。
- 首版展示与后续深度实验的 Gate 见 [共同路线图](../PROJECT_DIRECTION_AND_CHECKPOINTS.md)。

## 上游依据

以下为 2026-09-08 核对的官方说明，部署时以锁定版本再次验证：

- [项目与架构说明](https://github.com/GoogleCloudPlatform/microservices-demo)：提供电商流程、购物车 Redis 依赖及 Locust 负载生成器。
- [开发指南](https://github.com/GoogleCloudPlatform/microservices-demo/blob/main/docs/development-guide.md)：提供本地 Kubernetes 部署路径；完整项目的资源需叠加监控与 Agent 后实测。
- [Google Cloud Operations 组件](https://github.com/GoogleCloudPlatform/microservices-demo/blob/main/kustomize/components/google-cloud-operations/README.md)：默认关闭集成，文档标注当前支持范围有限，不据此假设所有信号开箱即用。
