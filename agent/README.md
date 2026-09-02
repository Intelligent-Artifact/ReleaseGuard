# ReleaseGuard Agent MVP

本目录已经包含一个可运行的发布回归 Agent。它不是通用聊天机器人，而是围绕 `payment-service` canary 回归执行受约束调查、人工审批和恢复验证。

## 已实现闭环

```text
DETECTED → COLLECTING → CORRELATING → DIAGNOSED → PROPOSED
                                                   ↓
                                      AWAITING_APPROVAL（持久化暂停）
                                                   ↓ 同一 thread_id 恢复
                                      EXECUTING → VERIFYING
                                                   ↓
                            RESOLVED | RECOVERY_FAILED | REJECTED | EXPIRED
```

- LangGraph 负责 `StateGraph`、SQLite checkpoint、`interrupt()` 暂停和 `Command(resume=...)` 恢复。
- LangChain 负责模型统一适配、Pydantic tool schema、`bind_tools()` 和 tool call 消息协议。
- 模型只绑定 `get_deployment` 与 `compare_metrics` 两个只读工具。
- rollback 不作为模型工具暴露；确定性策略判定为 `MEDIUM` 后，必须人工批准才能由图中的受控节点提交。
- `investigation_id` 同时作为 LangGraph `thread_id`，服务进程重启后仍可从 SQLite 恢复。
- Gateway 写请求使用由调查和 proposal 派生的稳定幂等键。
- 报告明确区分事实、推断、限制与建议，不会在缺少日志/trace 时声称已定位具体 SQL。

## 本地运行

要求 Python 3.11 或更高版本。

```powershell
cd agent
python -m pip install -e ".[test]"
python -m pytest
python -m releaseguard.demo
```

离线演示默认使用：

- `contracts/examples/deployment-response.json`；
- `contracts/examples/metrics-compare-response.json`；
- 一个实现 LangChain `BaseChatModel` 和 tool calling 协议的确定性夹具模型；
- `data/agent-checkpoints.sqlite` checkpoint 数据库。

因此无需模型密钥或真实基础设施即可验证完整暂停/恢复闭环。

## 启动 HTTP API

```powershell
cd agent
python -m uvicorn releaseguard.api:app --host 0.0.0.0 --port 8080
```

启动调查：

```powershell
$body = @{
  investigation_id = "inv_demo_001"
  environment = "demo"
  service = "payment-service"
  symptom = "canary p95 延迟违反 SLO，怀疑 slow SQL 发布回归"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/v1/investigations `
  -ContentType application/json `
  -Body $body
```

响应状态应为 `AWAITING_APPROVAL`，并带有 `interrupt.kind=HUMAN_APPROVAL_REQUIRED`。

批准并恢复：

```powershell
$approval = @{
  approved = $true
  approved_by = "demo-operator"
  token = "demo-short-lived-token"
  expires_at = (Get-Date).ToUniversalTime().AddMinutes(5).ToString("o")
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/v1/investigations/inv_demo_001/resume `
  -ContentType application/json `
  -Body $approval
```

读取状态与报告：

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/investigations/inv_demo_001
Invoke-WebRequest http://localhost:8080/api/v1/investigations/inv_demo_001/report
```

## 接入真实模型与 Gateway

从仓库根目录复制 `.env.example` 为 `.env`，再至少配置：

```dotenv
RELEASEGUARD_MODEL=openai:gpt-5-mini
OPENAI_API_KEY=你的短时效开发密钥
RELEASEGUARD_GATEWAY_MODE=http
RELEASEGUARD_GATEWAY_BASE_URL=http://ops-gateway:8081
RELEASEGUARD_GATEWAY_TOKEN=短时效服务令牌
```

`RELEASEGUARD_MODEL` 交给 LangChain `init_chat_model()`，因此后续可在不改图运行逻辑的前提下替换受支持的模型提供方。真实 Gateway 必须满足 `../contracts/openapi.yaml`；Agent 不会直连 Kubernetes、Prometheus 或 Loki。

## 当前限制

- 当前共享 OpenAPI 只冻结了部署、指标比较、rollback 与动作查询，因此 MVP 的根因结论只到“发布相关指标回归”，不会伪造 slow SQL 日志、trace 或 Git diff。
- HTTP Gateway 返回异步非终态时，本版会将恢复判定为失败；下一阶段应增加有上限的动作轮询或事件驱动唤醒。
- SQLite 适合本地 MVP。多副本部署应替换为 LangGraph Postgres checkpointer，但 `thread_id` 和恢复 API 不需要改变。
- production 审批 token 的签发与密码学校验属于 Gateway 职责；Agent 只校验存在性、绑定的 proposal 生命周期和过期时间。
