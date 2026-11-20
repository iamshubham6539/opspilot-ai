# Database connection problems

## Symptoms

- Requests fail with `connection pool exhausted`, `timeout acquiring connection`, or
  `too many clients already`.
- Error rates climb while CPU stays moderate; the app is waiting, not computing.
- Database connection metrics sit at or near the configured maximum.
- Latency rises in steps as the pool drains, then errors appear.

## Likely causes

- Pool size was lowered, or instance count was raised without adjusting the pool.
- A query or transaction is holding connections longer than expected (missing commit,
  long-running migration, lock wait).
- A downstream call inside a transaction keeps connections checked out during network waits.
- Database failover or restart drained connections faster than they could be re-established.

## Checks

1. Compare configured pool size with peak concurrent request volume.
2. Check `in_use` against `max` on each instance for the last 30 minutes.
3. Look for queries with long durations around the first error timestamps.
4. Confirm whether a deployment changed pool settings or the number of replicas.
5. Check the database for locks, idle-in-transaction sessions, and connection limits.

## Mitigation

- Roll back a recent pool-size or replica-count change if errors started right after it.
- Restarting instances sheds stuck connections, but it is a temporary fix and needs approval.
- Raise the pool size only after confirming the database can accept more connections.
- Reduce connection hold time by moving network calls out of transactions.

## Escalation

Escalate to the database on-call when the database itself reports connection limits, when
locks are involved, or when the pool is correctly sized and still exhausted.

## Do not

- Do not raise the pool beyond the database connection limit; that moves the failure to the
  database and can take down every service that shares it.
