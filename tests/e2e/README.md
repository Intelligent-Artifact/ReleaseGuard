# End-to-End Tests

Primary owners: [@Manticore0918](https://github.com/Manticore0918) and [@adminxue](https://github.com/adminxue)

End-to-end tests verify the complete ReleaseGuard workflow across ownership boundaries:

```text
deploy baseline
  → start workload
  → deploy candidate canary
  → inject fault
  → trigger investigation
  → collect grounded evidence
  → apply policy and approval
  → execute remediation
  → verify recovery
  → score and report
  → clean up
```

Tests must cover both successful and failed diagnosis/remediation paths. A command returning successfully is not sufficient; the test must verify rollout state, service health, SLO, minimum traffic, audit records, and cleanup.
