# Incident Scenarios

Primary owners: [@Manticore0918](https://github.com/Manticore0918) and [@adminxue](https://github.com/adminxue)

This directory contains versioned and reproducible incident definitions used by the ReleaseGuard evaluation lab.

## Required scenario fields

Each scenario should define:

- target environment, service, and release version;
- workload profile and preconditions;
- bounded injection method and parameters;
- expected symptoms and ground-truth root cause;
- evidence the Agent should be able to discover;
- acceptable and forbidden actions;
- recovery checks and thresholds;
- injection TTL and maximum MTTR;
- idempotent cleanup procedure.

## Safety rules

- Scenarios may affect only the dedicated demo environment.
- Every injection requires a maximum TTL and automatic cleanup.
- Preconditions must prove the baseline is healthy.
- Injection and cleanup must be independently verified.
- The Agent runtime must not be able to read ground-truth answers.
- Failed setup or cleanup must be visible in the evaluation result.

## Initial scenarios

1. Candidate-only slow SQL query.
2. Candidate memory leak.
3. Invalid environment configuration.
4. Database connection-pool exhaustion.
5. Redis outage.
6. Dependency timeout.
7. CPU saturation.
8. Incorrect Kubernetes resource limit.
9. Scoped DNS failure.
10. Degraded deployment/readiness failure.
