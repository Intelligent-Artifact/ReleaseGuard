# 旧发布闭环 v0.1 Contract 差距分析（历史快照）

> 关联 Issue：#4（冻结 v0.1 Agent↔Gateway HTTP contract）、#28（指标方向语义）
> 状态：2026-09-08 起作为历史快照保留，不再作为新监控主线的执行清单。

新方向与后续契约工作以[监控契约迁移计划](MONITORING_CONTRACT_PLAN.md)为准。
下文中的 v0.1、G2/G3、Issue 依赖和“下一步”均指旧发布回归方案；没有修改远端
Issue，也不表示已冻结相应接口。保留此快照用于理解已有讨论和复用通用契约要求。

## 1. 目标

本文档只回答一个问题：

> 要让 v0.1 的 Mock Gateway 与 Agent client 能够依据同一份 OpenAPI 完成
> “调查 → 建议 → 审批 → 幂等 rollback → 独立恢复验证”闭环，现有契约还缺什么？

本文档不直接修改 OpenAPI，也不实现代码。

## 2. 现有基线

`contracts/openapi.yaml`（v0.1 草案）当前包含：

| 方法 | 路径 | 当前覆盖 |
|---|---|---|
| GET | `/api/v1/deployments/{service}` | deployment + rollout 元数据 |
| GET | `/api/v1/metrics/compare` | baseline/candidate 指标对比 |
| POST | `/api/v1/actions/rollback` | rollback 请求（含 approval） |
| GET | `/api/v1/actions/{action_id}` | action 状态 |

已有 schema：

- `DeploymentResponse` / `ReleaseRevision`
- `MetricsCompareResponse` / `MetricComparison`
- `RollbackRequest` / `Approval`
- `ActionResponse`
- `ErrorResponse`

已有 fixture：

- `contracts/examples/deployment-response.json`
- `contracts/examples/metrics-compare-response.json`
- `contracts/examples/rollback-request.json`

## 3. v0.1 需要但当前缺失的能力

### 3.1 接口缺口

| 需要的能力 | 来源 | 已有契约基础 | 仍缺失的语义 |
|---|---|---|---|
| 有边界 logs 查询 | #16 / G2 | 无 | 查询接口与 fixture |
| Git change / commit metadata 查询 | #16 / G2 | 无 | 查询接口与 fixture |
| 独立 post-action recovery verification | #33 / G3 | 无 | 查询接口与独立判定语义 |
| action 幂等与冲突语义 | #32 / G3 | 已定义必填 `Idempotency-Key` header、`409 ActionConflict` response 与 `ACTION_ALREADY_RUNNING` 错误码 | 同 key 同 payload 重放、同 key 不同 payload、并发冲突等行为语义尚未显式定义 |
| approval approve/reject/expire 生命周期 | #31 / G3 | `Approval` 作为 rollback request 嵌套字段存在 | 独立状态转换接口与过期/拒绝/scope 越界语义 |

### 3.2 Schema 缺口

v0.1 需要的核心 schema 中，以下仍未进入 OpenAPI 的稳定定义：

- `Evidence`（稳定 `source_ref`、采集时间、查询参数、摘要与质量信息）
- `RCA`（假设、证据引用、置信度、未知项）
- `Decision`（`PROMOTE` / `HOLD` / `ROLLBACK` / `INCONCLUSIVE`）
- `ActionType`（v0.1 只允许 `ROLLBACK_RELEASE`）
- 可复用的 `ActionStatus` schema：当前 `ActionResponse.status` 已有 inline 枚举
  `ACCEPTED / RUNNING / VERIFYING / SUCCEEDED / FAILED / VERIFICATION_FAILED`，
  但尚未抽取为独立定义，也尚未与未来的 `RecoveryStatus` 明确解耦与迁移
- 明确的 `RecoveryStatus` / `RecoveryResult`
- 审批拒绝、过期与 scope 越界的稳定错误响应

### 3.3 指标方向语义缺口（#28）

当前 `MetricComparison` 只有数值与 `comparable`，没有声明每个指标“哪个方向代表退化”。
#28 的契约要求不仅是方向，还包括可让 Gateway 与 Agent 独立实现一致比较逻辑的完整语义：

例如：

- `availability` 从 0.999 降到 0.95 应视为退化；
- `request_rate` 上升不代表退化；
- `p95_latency` 上升才是退化。

需要补充/明确的语义：

- 每个指标的方向（lower is better / higher is better）；
- 回归阈值与单位；
- 比较窗口；
- 最小样本量；
- missing / uncomparable 行为；
- 方向缺失或单位不匹配时稳定降级为 `INCONCLUSIVE`；
- 让 Gateway/Agent 使用同一份定义，而不是各自硬编码。

## 4. 建议的拆分提交顺序

#4 是里程碑，不作为一个大 PR 提交。建议按以下顺序推进：

1. **核心枚举与基础 schema**
   - `Decision`、`ActionType`、`ActionStatus`、`RecoveryStatus`
   - 先在 OpenAPI 中成为稳定可引用定义
2. **领域 schema**
   - `Evidence`、`RCA`、`Approval`、`Action`、`RecoveryResult`
3. **日志与 Git Evidence 接口**
   - 新增 logs 查询与 Git change 查询的 contract 与 fixture
4. **动作生命周期与错误语义**
   - approve/reject/expire
   - 幂等键、冲突、缺失、超时、部分数据、schema mismatch 的稳定错误码
5. **示例与负向 fixture**
   - 更新 `contracts/examples/`
   - 为正常、缺失、超时、恶意日志、recovery failure 建立显式 fixture
   - 补充 OpenAPI lint / schema 校验

## 5. 需要双方先确认的开放问题

1. logs 与 Git 查询的最小参数集合是什么？
2. recovery verification 是独立 endpoint，还是复用 action status？
3. `ActionStatus` 是否需要包含 `PENDING_APPROVAL` / `APPROVED` / `REJECTED`，还是把它们放在 approval 状态机内？
4. 指标方向语义放在 OpenAPI schema 内，还是放在独立规则文件中？
5. 破坏性变更是否单独记录 ADR？

## 6. 本文档之后的下一步

基于本文档与 #28 一起确认后，开始第 1 个契约小 PR：

> 在 `contracts/openapi.yaml` 增加 v0.1 核心枚举，不涉及业务实现。
