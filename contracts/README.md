# Agent–Gateway Contracts

Primary owners: [@Manticore0918](https://github.com/Manticore0918) and [@adminxue](https://github.com/adminxue)

`openapi.yaml` is the source of truth for communication between the Agent and Ops Gateway.

## Change process

1. Describe the consumer need in a GitHub issue.
2. Update OpenAPI and an example fixture.
3. Agree on field semantics, missing-data behavior, limits, and error codes.
4. Implement provider and consumer against the same fixture.
5. Run contract and end-to-end tests.

Breaking changes must not be merged silently. Prefer additive, backward-compatible changes during the MVP.

## Contract principles

- Actions are typed; arbitrary shell or Kubernetes commands are forbidden.
- Every response has a request ID and generation time.
- Deployment and telemetry data identify environment, service, and version.
- Missing, stale, and partial data are represented explicitly.
- Action requests bind proposal, target, approval, and idempotency information.
- Clients branch on stable error codes, not human-readable error messages.

## Examples

- `examples/deployment-response.json`
- `examples/metrics-compare-response.json`
- `examples/rollback-request.json`
