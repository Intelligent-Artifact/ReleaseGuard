# 端到端测试

共同负责人：[@Manticore0918](https://github.com/Manticore0918) 和 [@adminxue](https://github.com/adminxue)

端到端测试用于验证跨越双方职责边界的完整 ReleaseGuard 流程：

```text
部署 baseline
  → 启动工作负载
  → 以 canary 方式部署 candidate
  → 注入故障
  → 触发调查
  → 收集有依据的证据
  → 应用策略并完成审批
  → 执行处置
  → 验证恢复
  → 评分并生成报告
  → 清理环境
```

测试必须同时覆盖诊断/处置成功和失败的路径。命令成功返回并不足以证明测试通过；还必须验证 rollout 状态、服务健康、SLO、最小流量、审计记录和清理结果。
