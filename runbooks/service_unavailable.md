# Service unavailable

## Symptoms

- Health checks fail and load balancers remove all instances.
- Callers receive 502, 503, or connection refused.
- One service returns errors for every request, not a subset.
- Kubernetes or the process supervisor reports crash loops, failed readiness, or OOM kills.

## Likely causes

- A deployment or configuration change that prevents the service from starting.
- All instances unhealthy because of a shared dependency (database, cache, DNS, secrets).
- Resource exhaustion: memory limit, file descriptors, disk space, or certificate expiry.
- A failed migration or a startup check that never passes.
- Network policy or ingress change blocking traffic.

## Checks

1. Read startup logs from the newest instances; look for configuration, migration, or secret errors.
2. Confirm the last deployment and whether the previous version was healthy.
3. Check health endpoint output and readiness probe configuration.
4. Verify shared dependencies are reachable from the service's network.
5. Check disk, memory, and certificate expiry on the hosts.

## Mitigation

- Roll back the most recent deployment if the failure started with it; this is the fastest
  reversible action and requires approval.
- Restore the dependency or configuration that blocks startup, then restart instances.
- Restarting without fixing the cause will usually crash-loop again; read the logs first.
- If only one availability zone is affected, fail traffic over to healthy zones.

## Escalation

Escalate to the platform team when DNS, ingress, or cluster scheduling is involved.
Escalate to security when certificates or secrets are the cause.

## Do not

- Do not delete instances or volumes to "clean up" during an incident.
- Do not disable health checks to force traffic back onto failing instances.
