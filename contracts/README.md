# Agent–Gateway 契约

共同负责人：[@Manticore0918](https://github.com/Manticore0918) 和 [@adminxue](https://github.com/adminxue)

[`openapi.yaml`](openapi.yaml) 是已提交 API 契约的唯一事实来源。当前它仍是发布回归 `/api/v1` 草案，包含部署、baseline/candidate 指标比较、rollback 请求与动作状态；不代表监控主线已经实现。

## 监控迁移

新的产品 v0.1 计划使用 Online Boutique 的真实监控事件和只读调查。新增事件、指标/日志/资源查询、人工干预记录和独立恢复能力，拟以 `/api/v2` 与旧行为并存，具体设计见[监控契约迁移计划](MONITORING_CONTRACT_PLAN.md)。产品版本和 API 版本分别管理。

本次只更新计划，不修改 OpenAPI、fixture 或运行时。旧路径与测试保留兼容，新监控 schema、路径和 fixture 需先经 G1 双方签收。自动动作及审批在产品 v0.3 单独冻结。

[旧 v0.1 差距分析](V01_CONTRACT_GAP.md) 是发布闭环的历史快照，不再驱动新主线。

## 变更流程

1. 在工作项中说明消费方需求、owner、依赖与验收标准。
2. 更新 OpenAPI 和正反示例，明确属于旧发布能力还是新监控能力。
3. 对齐事件身份、scope、时间窗、缺失语义、限制和错误码。
4. 提供方与消费方按同一测试夹具分别实现，互相 review。
5. 运行契约测试和相应跨边界测试，新旧版本同时验证。

不得静默删除必填字段、改变枚举或重新解释旧字段。破坏兼容性时使用新 API 版本或双方明确签收的迁移方案。

## 新监控契约原则

- 告警、调查、人工干预、后续动作和恢复分别建模，通过稳定 ID 关联。
- scope 包含 environment、cluster、namespace 和服务/资源，证据具有时间窗与来源。
- version、deployment 和 Git 为可选上下文，无发布事故也可调查；旧 `/api/v1` 必填语义保持不变。
- 指标声明单位、方向、参照、样本和阈值；无数据、过期、部分返回、不可比均显式表达。
- 查询模板与参数受限，禁止自由 shell、PromQL、LogQL 或任意资源 patch。
- 人工干预记录只能由独立操作者提交，Agent 只读；操作声明不等于恢复证据。
- 后续写动作必须绑定 proposal、明确目标、审批、前置状态与幂等信息。
- 客户端按稳定错误码处理，不解析面向人的错误文本。

## 当前发布 fixture

以下示例仍用于旧开发预览与兼容性测试：

- [deployment-response.json](examples/deployment-response.json)
- [metrics-compare-response.json](examples/metrics-compare-response.json)
- [rollback-request.json](examples/rollback-request.json)

监控主线的新示例在契约实现任务中添加，不以修改旧 fixture 的 service/version 标签伪造 Online Boutique 接入。
