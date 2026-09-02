# Agent–Gateway 契约

共同负责人：[@Manticore0918](https://github.com/Manticore0918) 和 [@adminxue](https://github.com/adminxue)

`openapi.yaml` 是 Agent 与 Ops Gateway 通信的唯一事实来源。

## 变更流程

1. 在 GitHub Issue 中说明消费方需求。
2. 更新 OpenAPI 和对应的示例测试夹具。
3. 对齐字段语义、缺失数据行为、限制和错误码。
4. 提供方与消费方根据同一测试夹具实现。
5. 运行契约测试和端到端测试。

不得静默合并破坏兼容性的变更。MVP 阶段应优先采用可向后兼容的增量变更。

## 契约原则

- 动作必须类型化，禁止执行任意 shell 或 Kubernetes 命令。
- 每个响应都包含请求 ID 和生成时间。
- 部署与遥测数据必须标识 environment、service 和 version。
- 缺失、过期和部分数据必须明确表达。
- 动作请求必须绑定 proposal、target、approval 和幂等信息。
- 客户端根据稳定错误码判断，不能解析面向人的错误信息。

## 示例

- `examples/deployment-response.json`
- `examples/metrics-compare-response.json`
- `examples/rollback-request.json`
