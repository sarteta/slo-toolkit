"""Generate Prometheus recording + alerting rules from an SLO spec.

The output mirrors the structure popularized by Sloth and Pyrra:
- Recording rule: SLI value over a 5m window
- Recording rule: error budget burn rate over short and long windows
- Alerting rules: page on fast burn, ticket on slow burn

The fast/slow burn-rate thresholds use the multi-window multi-burn-rate
recipe from the Google SRE workbook (chapter 5):

  fast: burn rate >= 14.4 over 5m AND >= 14.4 over 1h    -> page
  slow: burn rate >= 6   over 30m AND >= 6   over 6h     -> ticket

Reference: https://sre.google/workbook/alerting-on-slos/
"""
from __future__ import annotations

from dataclasses import asdict
import yaml

from .spec import SLO, Spec


WINDOW_TO_SECONDS = {
    "7d": 7 * 24 * 3600,
    "28d": 28 * 24 * 3600,
    "30d": 30 * 24 * 3600,
    "90d": 90 * 24 * 3600,
}


def _sli_expr(slo: SLO) -> str:
    """Build the PromQL expression that yields the *current* SLI value
    in [0, 1] (where 1 = perfect)."""
    sli = slo.sli
    if sli.kind == "ratio":
        return (
            f"(({sli.good_events}) / clamp_min(({sli.valid_events}), 1))"
        )
    if sli.kind == "latency_threshold":
        # We treat the SLI as the fraction of requests faster than threshold.
        # The user provided a quantile query -- we adapt it: the ratio of
        # fast requests can be computed differently in practice. Here we
        # generate an alerting expression that fires when the quantile
        # exceeds the threshold for a sustained period. Recording rule
        # name still emits the quantile value for dashboards.
        return f"({sli.query})"
    raise ValueError(f"unknown SLI kind {sli.kind}")


def _alert_expr(slo: SLO, *, short_window: str, long_window: str, burn_rate: float) -> str:
    """For ratio SLIs, the burn-rate alert fires when both windows exceed
    the burn-rate threshold."""
    sli = slo.sli
    if sli.kind == "ratio":
        # burn = (1 - SLI) / (1 - objective/100)
        eb = 1 - slo.objective / 100.0
        # We use rate() with the window override
        good_short = sli.good_events.replace("[5m]", f"[{short_window}]")
        valid_short = sli.valid_events.replace("[5m]", f"[{short_window}]")
        good_long = sli.good_events.replace("[5m]", f"[{long_window}]")
        valid_long = sli.valid_events.replace("[5m]", f"[{long_window}]")
        return (
            f"((1 - (({good_short}) / clamp_min(({valid_short}), 1))) / {eb:.6f}) > {burn_rate}\n"
            f"        and\n"
            f"        ((1 - (({good_long}) / clamp_min(({valid_long}), 1))) / {eb:.6f}) > {burn_rate}"
        )
    if sli.kind == "latency_threshold":
        # For latency, we alert if the p-quantile is above the threshold
        # for a sustained period. burn_rate isn't strictly applicable here,
        # but we keep the multi-window discipline.
        return (
            f"({sli.query}) > {sli.threshold_seconds}\n"
            f"        and\n"
            f"        ({sli.query.replace('[5m]', f'[{long_window}]')}) > {slo.sli.threshold_seconds}"
        )
    raise ValueError(f"unknown SLI kind {slo.sli.kind}")


def _common_labels(spec: Spec, slo: SLO) -> dict[str, str]:
    base = {"service": spec.service, "owner": spec.owner, "slo": slo.name}
    base.update(slo.labels)
    return base


def build_rules(spec: Spec) -> dict:
    """Return the YAML-ready dict that goes into a Prometheus rules file."""
    groups: list[dict] = []
    for slo in spec.slos:
        common = _common_labels(spec, slo)
        recording = {
            "name": f"slo:{spec.service}:{slo.name}:recording",
            "interval": "30s",
            "rules": [
                {
                    "record": f"slo:sli_value:{slo.name}",
                    "expr": _sli_expr(slo),
                    "labels": common,
                },
                {
                    "record": f"slo:objective:{slo.name}",
                    "expr": str(slo.objective),
                    "labels": common,
                },
            ],
        }
        alerting = {
            "name": f"slo:{spec.service}:{slo.name}:alerting",
            "rules": [
                {
                    "alert": f"SLOFastBurn_{slo.name}",
                    "expr": _alert_expr(slo, short_window="5m", long_window="1h", burn_rate=14.4),
                    "for": "2m",
                    "labels": {**common, "severity": "page", "burn_rate": "fast"},
                    "annotations": {
                        "summary": f"{spec.service} {slo.name}: fast error-budget burn",
                        "description": (
                            f"At current rate, the {slo.window} error budget for "
                            f"{slo.name} ({slo.objective}% objective) will be exhausted "
                            "in under 2 days. Multi-window 5m + 1h burn ≥ 14.4."
                        ),
                    },
                },
                {
                    "alert": f"SLOSlowBurn_{slo.name}",
                    "expr": _alert_expr(slo, short_window="30m", long_window="6h", burn_rate=6),
                    "for": "15m",
                    "labels": {**common, "severity": "ticket", "burn_rate": "slow"},
                    "annotations": {
                        "summary": f"{spec.service} {slo.name}: slow error-budget burn",
                        "description": (
                            f"Sustained moderate consumption of the {slo.window} error "
                            f"budget for {slo.name} ({slo.objective}% objective). "
                            "Investigate before it escalates."
                        ),
                    },
                },
            ],
        }
        groups.extend([recording, alerting])

    return {"groups": groups}


def render_yaml(spec: Spec) -> str:
    return yaml.dump(build_rules(spec), sort_keys=False, default_flow_style=False)
