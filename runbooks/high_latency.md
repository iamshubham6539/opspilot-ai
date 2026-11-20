# High latency

## Symptoms

- p95 or p99 latency rises above the service objective while error rates stay low.
- Requests complete, but slowly; timeouts appear at the edge or in callers.
- Queue depth, thread pool saturation, or connection wait times climb.
- Latency often starts at a specific time and affects one endpoint or dependency.

## Likely causes

- Slow database queries after a schema, index, or data-volume change.
- A dependency (inventory, payments, shipping) responding slower than usual.
- CPU or memory pressure on one instance, or uneven load balancing.
- Connection pool contention causing requests to wait for a connection.
- A recent deployment adding synchronous work to the request path.

## Checks

1. Break latency down by endpoint and by instance; if only one instance is slow, look at the host.
2. Check dependency latency and timeout rates for the same window.
3. Review slow queries and query plans for endpoints with the largest regression.
4. Compare the start time with deployments and feature-flag changes.
5. Check thread pool or event-loop saturation and garbage collection pauses.

## Mitigation

- Roll back the deployment or flag that introduced the regression if timing matches.
- Add or tune an index for the slow query after confirming the plan.
- Reduce load on the slow dependency with caching or by disabling non-critical work.
- Scale out only when the bottleneck is the application tier, not a shared dependency.

## Escalation

Escalate to the owning team of the slow dependency when its latency explains the incident.
Escalate to the database team when query plans or locks are implicated.

## Do not

- Do not raise timeouts as the first fix; it hides the regression and increases load.
- Do not scale out a service whose database is the bottleneck; it multiplies contention.
