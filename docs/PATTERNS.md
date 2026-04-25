# SLO patterns

Common SLO definitions I've found useful in production. Drop these into
your `slos:` block and adjust the PromQL labels to match your service.

The objective values here are starting points, not gospel. Tune them
based on (a) what your users actually notice, and (b) what you can
sustain without burning out the team.

## HTTP service availability

The bread-and-butter SLO. Every web service has a version of this.

```yaml
- name: availability
  objective: 99.9          # ~43 min/month error budget
  window: 30d
  sli:
    kind: ratio
    good_events: 'rate(http_requests_total{job="$SERVICE",status!~"5.."}[5m])'
    valid_events: 'rate(http_requests_total{job="$SERVICE"}[5m])'
```

**Tuning notes:**

- `99.9` is a reasonable starting target for a customer-facing API. If
  your API is internal-only and degradation is tolerable, start at `99`.
- Excluding `5xx` from `good_events` is correct for most cases. If you
  also want to flag client errors that indicate a backend bug (`400` on
  valid input, `429` due to broken rate limiting), narrow the regex
  further.
- If you have multiple endpoints with different criticality, define
  per-route SLOs rather than one global. A failed health-check endpoint
  shouldn't burn the same budget as a failed checkout endpoint.

## P95 / p99 latency threshold

Useful when "fast enough" is part of the contract.

```yaml
- name: latency-p95-500ms
  objective: 99
  window: 28d
  sli:
    kind: latency_threshold
    query: 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="$SERVICE"}[5m])))'
    threshold_seconds: 0.5
```

**Tuning notes:**

- Pick the percentile that matches the user pain you want to bound.
  P95 catches "noticeable slowness", p99 catches "bad day for the
  worst customer". P99.9 starts being noisy unless you have lots of
  traffic.
- Threshold should be 1.5-2x your typical latency, not your best case.
  If your service usually runs at 200ms p95, set the threshold at
  500ms -- leaves room for legitimate spikes (cold caches, rolling
  deploys) without false alerts.
- Latency SLOs and availability SLOs are independent error budgets.
  Don't double-count: a 5xx response shouldn't count toward both
  budgets being burned.

## Background job freshness

For data pipelines, ETL jobs, sync engines.

```yaml
- name: nightly-sync-fresh
  objective: 99
  window: 30d
  sli:
    kind: ratio
    # 1 if the most recent successful sync finished within the last 26h, else 0
    good_events: '(time() - (max_over_time(sync_last_success_timestamp_seconds[26h])) < 93600)'
    valid_events: '1'
```

**Tuning notes:**

- The "valid_events: 1" trick treats every scrape as a valid event,
  effectively measuring "what fraction of the time the data was fresh".
- Choose the freshness window slightly larger than your job's expected
  cadence + tolerance. Daily job → 26h window (cron + 2h grace).
- If your job has retries, only count the FINAL outcome. Don't burn
  budget on retries that succeed.

## Webhook delivery success

For systems that deliver events out (Stripe → your app, your app →
customer endpoints, etc.).

```yaml
- name: webhook-delivery
  objective: 99.5
  window: 7d
  sli:
    kind: ratio
    good_events: 'rate(webhook_deliveries_total{outcome="success"}[5m])'
    valid_events: 'rate(webhook_deliveries_total{}[5m])'
```

**Tuning notes:**

- `99.5` is the standard for outgoing webhooks. Higher than that and
  you're penalizing yourself for upstream failures.
- Use a 7d window for outgoing webhooks. Customer-side outages are
  short-lived; a 30d window dilutes the signal too much.
- Make sure `outcome="success"` only includes 2xx responses from the
  receiver. 4xx from the receiver is "they rejected our payload" --
  that's their bug, but it still counts as a failed delivery for your
  observability.

## Background queue freshness (consumer lag)

For Kafka/Kinesis/RabbitMQ consumers.

```yaml
- name: consumer-lag-under-30s
  objective: 99
  window: 30d
  sli:
    kind: latency_threshold
    query: 'max(kafka_consumer_lag_seconds{group="$GROUP"})'
    threshold_seconds: 30
```

**Tuning notes:**

- Lag-based SLOs are sensitive to redeploys (consumer restarts cause
  lag spikes that recover quickly). The multi-window burn-rate alerting
  in this toolkit handles that -- short-window blips don't fire pages.
- If your topic has dozens of partitions, `max` over partitions is
  usually what you want for SLO purposes -- the slowest partition
  defines user-visible lag.

## What I avoid

- **SLOs against synthetic checks alone.** If your only signal is
  Pingdom/Uptime Robot, the SLO is measuring "did the synthetic
  check pass" not "is the service good for users". Backfill with
  request-rate SLIs ASAP.
- **Per-developer SLOs.** SLOs measure user impact, not engineering
  effort. Tying performance reviews to SLOs is the fastest way to
  end up with under-tuned objectives.
- **SLO targets above the actual SLA.** If your contract says 99.9%,
  set SLO at 99.95%. Burning the SLO budget should not yet be
  customer-facing -- it's the heads-up before that.
