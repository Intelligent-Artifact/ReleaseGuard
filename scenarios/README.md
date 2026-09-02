# 事故场景

共同负责人：[@Manticore0918](https://github.com/Manticore0918) 和 [@adminxue](https://github.com/adminxue)

本目录用于存放 ReleaseGuard 评测实验室使用的版本化、可重复事故定义。

## 场景必填字段

每个场景应定义：

- 目标 environment、service 和发布版本；
- 工作负载配置和前置条件；
- 有边界的注入方式和参数；
- 预期症状和真实根因；
- Agent 应能发现的证据；
- 允许和禁止的动作；
- 恢复检查和阈值；
- 注入 TTL 和最大 MTTR；
- 幂等清理流程。

## 安全规则

- 场景只能影响专用 Demo 环境。
- 每次注入都必须设置最大 TTL 并支持自动清理。
- 前置检查必须证明 baseline 健康。
- 注入和清理结果必须独立验证。
- Agent 运行时不得读取 ground truth。
- 初始化或清理失败必须显示在评测结果中。

## 初始场景

1. 仅 candidate 出现的 slow SQL 查询。
2. candidate 内存泄漏。
3. 错误环境变量。
4. 数据库连接池耗尽。
5. Redis 不可用。
6. 下游依赖超时。
7. CPU 饱和。
8. Kubernetes 资源限制错误。
9. 受控范围内的 DNS 故障。
10. 部署或 readiness 退化。
