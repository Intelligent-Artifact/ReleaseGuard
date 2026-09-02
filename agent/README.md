# Agent

Primary owner: [@Manticore0918](https://github.com/Manticore0918)

This directory will contain the ReleaseGuard Agent application:

- investigation state machine;
- Ops Gateway tool clients;
- deployment and telemetry correlation;
- structured evidence and root-cause findings;
- deterministic risk policies and human approval lifecycle;
- recovery assessment and incident reports;
- incident replay runner and evaluation metrics.

## Boundary

The Agent must not call Kubernetes, Docker, Argo, Prometheus, or Loki directly in production-like flows. It consumes the versioned contract in `../contracts/openapi.yaml` through the Ops Gateway.

The Agent may propose an action. The platform independently validates policy, approval, target state, idempotency, execution, and recovery.

## Initial backlog

1. Define Investigation, Evidence, Finding, and ActionProposal models.
2. Implement an in-memory investigation state machine.
3. Generate a Markdown incident report from contract fixtures.
4. Implement deployment and metrics clients against the mock contract.
5. Add deterministic risk classification and approval states.
6. Run the slow-SQL scenario end to end.

See [the Agent engineering playbook](../docs/AGENT_ENGINEER_PLAYBOOK.md) for the complete plan.
