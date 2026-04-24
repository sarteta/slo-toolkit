# slo-toolkit

[![tests](https://github.com/sarteta/slo-toolkit/actions/workflows/tests.yml/badge.svg)](https://github.com/sarteta/slo-toolkit/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org)
[![license](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

A small CLI that turns a YAML SLO spec into:

- A Prometheus rules file with **multi-window multi-burn-rate** alerts
  (the recipe from Google's SRE workbook chapter 5).
- A Grafana dashboard JSON, one row per SLO with SLI, objective, and
  error-budget remaining panels.

Drop the generated files into your existing Prometheus + Grafana stack
and you're done. No daemon to run, no controller to install, no SaaS.

![demo](./examples/demo.png)

## Why I wrote this

I needed SLOs in a hurry on a contract last year. Observability was
fragmented across CloudWatch + Grafana + ad-hoc Prometheus, MTTR was
high, the usual. I started copy-pasting recording-rule templates from
one service to the next and fixing typos every time. Two weeks of
that and the YAML schema basically wrote itself.

Looked at Sloth and Pyrra — both well done, both CRDs, which means
a controller in the cluster I'd have to operate. For a few SLOs
across a handful of services, a CLI that emits plain YAML+JSON costs
nothing to run and lives in the service repo where it belongs.

## Spec example

```yaml
service: payments-api
owner: platform-team

slos:
  - name: availability
    objective: 99.9
    window: 30d
    sli:
      kind: ratio
      good_events: 'rate(http_requests_total{job="payments-api",status!~"5.."}[5m])'
      valid_events: 'rate(http_requests_total{job="payments-api"}[5m])'
    labels:
      tier: critical
      pagerduty_service: payments

  - name: latency-p95-500ms
    objective: 99
    window: 28d
    sli:
      kind: latency_threshold
      query: 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="payments-api"}[5m])))'
      threshold_seconds: 0.5
```

## Run

```bash
pip install -e .
slo-toolkit --spec examples/payments-api.yml --out-dir build/
```

Output:

```
build/
├── payments-api-slos.yml         # drop into prometheus rule_files
└── payments-api-dashboard.json   # import into Grafana
```

## What gets generated for each SLO

**Recording rules** — track SLI value and objective for downstream consumers:

```yaml
- record: slo:sli_value:availability
  expr: (rate(...good...) / clamp_min(rate(...valid...), 1))
- record: slo:objective:availability
  expr: 99.9
```

**Alerting rules** — the multi-window multi-burn-rate pattern:

```yaml
- alert: SLOFastBurn_availability
  expr: burn_rate_over_5m > 14.4 AND burn_rate_over_1h > 14.4
  labels: { severity: page, burn_rate: fast }

- alert: SLOSlowBurn_availability
  expr: burn_rate_over_30m > 6 AND burn_rate_over_6h > 6
  labels: { severity: ticket, burn_rate: slow }
```

The thresholds (14.4 fast, 6 slow) come from the [SRE workbook chapter 5](https://sre.google/workbook/alerting-on-slos/) and are encoded as a regression test so they don't drift.

## Validation

The example output passes `promtool check rules` cleanly:

```bash
$ promtool check rules build/payments-api-slos.yml
SUCCESS: 12 rules found
```

That check is part of CI on every push.

## Tests (24)

- Spec loading: rejects bad windows, out-of-range objectives, invalid
  names, duplicates, unknown SLI kinds, missing latency thresholds
- Prometheus output: two rule groups per SLO, correct burn-rate
  thresholds (regression-tested), labels inherited from the spec
- Grafana output: three panels per SLO, unique panel IDs, thresholds
  reflect the SLI's objective
- CLI: writes both files, `--prom-only` and `--grafana-only` flags,
  exit code 2 on bad spec

```bash
pytest tests/ -v
```

## Design choices

A few things worth calling out, in case you're considering this for
real use.

**One config in, two configs out.** No state machine, no controller
pulling from a CRD. The spec is YAML in your repo. The output is
YAML+JSON in your repo. Diffs go through normal review. If the
toolkit gets retired, the generated files keep working unchanged.

**Multi-window multi-burn-rate, not single-threshold alerts.** Single
threshold SLO alerts age badly — they spam during minor blips or
sleep through real outages. The Google recipe gives you two windows
per severity, which is the kind of thing that sounds like an academic
detail until you've been paged at 4am for a transient network blip.

**Two SLI kinds: ratio + latency_threshold.** Covers maybe 90% of
what people actually deploy. Window-based SLIs and bucket-fraction
SLIs are rare enough that I didn't bother — the `SLI` dataclass is
30 lines, extend it if you need.

**`clamp_min(denominator, 1)` everywhere.** Naive ratio rules divide
by zero when your service has no traffic, and AlertManager treats
the resulting NaN as a flap. Clamp fixes this without distorting
real measurements (1 request vs 1000 requests both yield the right
ratio; 0 requests yields a "perfect" 1.0 instead of an alert storm).

## Roadmap

- [ ] Burn-rate alert tuning per window length (the workbook has a
      table for 28d/30d/90d combinations)
- [ ] OpenSLO compatibility — accept the OpenSLO YAML as input too
- [ ] Sloth-format export for users already on Sloth
- [ ] Datadog monitor JSON output

## License

MIT © 2026 Santiago Arteta
