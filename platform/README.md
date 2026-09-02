# Platform

Primary owner: [@adminxue](https://github.com/adminxue)

This directory will contain the ReleaseGuard runtime and reliability platform:

- demo microservices and stateful dependencies;
- Docker Compose and Kubernetes deployment;
- Helm, Argo CD, and Argo Rollouts;
- Prometheus, Grafana, Loki, and OpenTelemetry;
- the constrained Ops Gateway;
- workload generation and fault injection;
- policy enforcement, RBAC, action audit, and recovery verification.

## Boundary

The platform exposes only versioned, structured capabilities defined in `../contracts/openapi.yaml`. It must not execute arbitrary commands supplied by the Agent.

Read and write identities must be separated. Mutating actions must be allowlisted, idempotent, auditable, and independently verified after execution.

## Initial backlog

1. Bootstrap three minimal demo services with health, metrics, and structured logs.
2. Build the Docker Compose development platform.
3. Implement deployment metadata and metric comparison endpoints.
4. Add a stable k6 checkout workload.
5. Implement the slow-SQL scenario with TTL and cleanup.
6. Add policy-gated rollback and recovery verification.

See [the DevOps/Platform engineering playbook](../docs/DEVOPS_PLATFORM_PLAYBOOK.md) for the complete plan.
