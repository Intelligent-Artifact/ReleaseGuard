# 监控主线契约迁移计划

> 日期：2026-09-08<br>
> 状态：待 G1 联合冻结的设计输入；下列新路径、字段和枚举尚未实现。<br>
> 共同负责人：@Manticore0918、@adminxue

## 1. 目标与兼容边界

使没有新发布的监控事件也能进入调查，并经同一 HTTP 边界读取证据、记录人工干预和验证恢复。Online Boutique 是被监控业务，Ops Gateway 仍由本项目实现。

当前 `openapi.yaml` 的 `/api/v1`、发布 fixture、CP0 Mock 和 Agent smoke 行为保持不变。监控能力拟在同一 OpenAPI 文件中新增 `/api/v2`，避免改变 `/metrics/compare` 必填参数或重新解释旧枚举。产品 `v0.1` 指作品集阶段，与 HTTP API v2 无冲突。

本次计划改动不更新 OpenAPI，不生成新的假响应，不修改 client 或模型。G1 的契约 PR 才使新定义成为事实来源；旧路径不再驱动新主线，后续退役需明确迁移与消费方验收。

## 2. 首版拟定的能力边界

| 提供方 | 拟定方法 / 路径 | 目的与关键约束 |
|---|---|---|
| Gateway | `POST /api/v2/alert-events` | 接收授权 Alertmanager 通知，拆分、保存、精确去重；Agent 无权伪造 live 告警 |
| Gateway | `GET /api/v2/incidents` | 受限分页与游标，供 Agent 自动轮询；事件状态筛选不代替投递游标 |
| Gateway | `GET /api/v2/incidents/{incident_id}` | 当前事件、scope、firing/resolved 时间线和来源 |
| Gateway | `GET /api/v2/metrics` | 固定模板、service/resource、起止时间；参照可为 SLO/历史窗口/健康实例，version 可选 |
| Gateway | `GET /api/v2/logs` | 固定过滤、窗口、数量/字节限制、聚合与原始引用 |
| Gateway | `GET /api/v2/resources` | scope 内依赖关系、UID、运行状态及事件；区分静态拓扑与观测 |
| Gateway | `POST /api/v2/manual-interventions` | 独立操作者记录已执行操作，Agent 无此写权限；此端点不执行基础设施动作 |
| Gateway | `GET /api/v2/incidents/{incident_id}/recovery` | 返回独立验证状态、检查与来源；验证任务由有效人工记录触发，GET 不重复发起任务 |

Agent 对 Gateway 只有读取权限，内部按 incident ID 创建唯一调查。Gateway 保存告警后确认投递，Agent 记录消费游标及调查创建结果；具体原子性、重试与唯一约束在 G1 fixture 中冻结。v0.1 允许中断后显式重新运行，不能重复创建同事故的活动调查；v0.2 增加自动续跑。

人工干预端点需绑定操作者身份、incident、资源 UID、目标与操作时间，且符合范围限制。它保存的是人工声明，不是恢复证据，也不提供任意命令执行。Gateway 验证器异步采集新窗口，与人工记录关联后返回恢复状态。

traces 在 v0.2 增加；审批、action submit/status 在 v0.3 单独冻结；部署/Git 与版本比较专项在 v1.0 扩展。旧 rollback Mock 的存在不表示 v0.1 live Gateway 开放写动作。

## 3. 最小公共语义

### 3.1 事件身份与状态

- `incident_id`、来源、environment/cluster/namespace、受影响 service、fingerprint、startsAt、receivedAt、可选 endsAt。
- 同来源和 scope 下的 fingerprint + startsAt 标识同一次告警事件；重复通知不新建事故。
- resolved 更新事件，不自动标记调查已恢复；乱序 firing 不重开同一次旧事件。
- 新 startsAt 表示后续新故障，必须有新 incident ID；跨服务聚合在 v0.2 实现。
- 入口校验缺失时间、非法 scope 和不可信 label，明确拒绝或隔离规则，不能任意合并。

### 3.2 查询与证据

- 响应包含 `request_id`、`generated_at`、scope、查询窗口、稳定 source reference 和质量警告。
- Evidence 有 ID、来源类型、资源/服务、observed/collected 时间、单位、样本量、摘要与取回引用。
- version、commit、deployment 为可选上下文；缺失不阻塞服务运行故障调查。
- 指标明确方向、阈值、单位、样本分母、最小样本和参照类型；请求量本身没有统一退化方向。
- 区分有效空结果、无数据、采集失败、过期、部分返回和不可比；缺单位或缺方向时不得自行判定正常。
- 跨服务证据需有依赖依据，scope 由授权和程序固定；同一指标派生的告警与指标不算独立来源。
- 原始引用只经授权取回，不允许模型提交任意文件路径或 URL。

### 3.3 诊断、响应与恢复

以下枚举为拟定监控语义，尚未进入代码：

| 概念 | v0.1 / v0.2 值 | 解释 |
|---|---|---|
| DiagnosisStatus | `CONFIRMED / INCONCLUSIVE / NO_INCIDENT` | 根因可证实、证据不足、有效证据未验证到异常 |
| ResponseDisposition | `OBSERVE / MANUAL_REQUIRED` | 继续观察或要求人工处理；v0.3 才加 `PROPOSE_ACTION` |
| RecoveryStatus | `NOT_REQUESTED / VERIFYING / RECOVERED / NOT_RECOVERED / INCONCLUSIVE` | 是否已请求检查、正在观察、恢复、未恢复或无法判断 |

报告状态、诊断状态与恢复状态独立。证据不足也能生成报告，但不能自动变成 `NO_INCIDENT` 或 `RECOVERED`。已发生的故障在恢复后仍保留诊断记录。

人工记录有 `intervention_id`、操作者身份、incident、目标、发生/记录时间、操作说明及结果引用；禁止由 Agent 写入。验证结果引用该记录及新的遥测窗口，并列明每项检查、阈值、实际值、样本和来源。TTL 清理记录有独立执行来源，不能算作人工或 Agent 修复。

## 4. v0.3 动作契约的后续边界

后续单独定义 Approval、ActionProposal、Action 与 RecoveryResult。首个写动作仅限已审核无状态 Deployment 的副本数恢复，具有目标 UID、预期当前值、明确目标值、上限、有效期和 payload hash。

审批 approve/reject/expire 与执行 accepted/running/succeeded/failed 分离；实际枚举由该阶段契约 PR 冻结。相同幂等键和 payload 返回同 action；不同 payload 冲突；一次审批不得创建第二个动作。已授权动作的状态查询与幂等重试不应因审批已消费而失去可查询性。

执行器必须重新校验 scope、策略、审批和目标状态；状态变化需重新评估，不得直接沿用旧批准。执行成功不表示恢复成功；恢复仍通过独立检查返回。

## 5. 实施与验证顺序

| 工作项 | Owner | 验收 |
|---|---|---|
| 固定事件与证据样本，确认语义缺口 | 双方，平台采样 | G0 的真实健康/异常数据与覆盖矩阵 |
| 新增监控 schema、API 与 fixture | 双方 | OpenAPI 校验，新旧 schema 测试同时通过 |
| Gateway 事件/HTTP fixture、Agent client 与消费测试 | 各自实现，交叉 review | 自动触发、精确去重、分页/乱序/重试语义 |
| 接入真实指标、日志、资源适配 | 平台，Agent 验收 | fixture 与 live 同 schema，缺失/部分/超时明确 |
| 迁移无版本调查与多源 grounding | Agent | 没有 candidate/Git 也能调查，跨 scope 证据被拒绝 |
| 人工记录、恢复验证与 E2E | 平台与 Agent | 假恢复、无流量、TTL 归因及实际恢复测试 |

单个工作项可拆为多个小 PR，避免把 schema、模型、业务逻辑与基础设施混成一个大改动。若已被其他分支实现，先核对实际接口再更新计划，不重复覆盖。

## 6. G1 必须补齐的正反 fixture

- 无发布事件，Redis 故障涉及 cartservice 与 redis-cart 两个资源。
- firing 重复、resolved 先到、旧 firing 重发、同 fingerprint 新 startsAt、不同 scope 同 fingerprint。
- 指标缺失、过期、单位不一致、低样本、日志截断、依赖范围越界和后端超时。
- 不可信日志试图更改工具、目标或指令。
- 人工记录无权限或目标不匹配、操作成功但业务未恢复、告警 resolved 但样本不足。
- TTL 自动清理先发生、采集器中断、恢复窗口尚未结束。

## 7. 旧计划的处理

`V01_CONTRACT_GAP.md` 保留为旧发布闭环差距快照，其 Issue 编号不等于新阶段依赖。重新核对现有 backlog：证据质量、错误语义、HTTP client 可复用；强制 Git 和版本比较要改写；审批/rollback 延后到对应深度阶段。

本文件记录迁移输入，`openapi.yaml` 始终是已提交运行契约的事实来源。双方签收契约后才实现消费方与提供方，不能根据本草案悄悄改变旧路径行为。
