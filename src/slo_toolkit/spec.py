"""SLO spec -- the minimal YAML schema this toolkit consumes.

Example:

    service: payments-api
    owner: platform-team
    slos:
      - name: availability
        objective: 99.9            # percent over the window
        window: 30d                # 7d | 28d | 30d | 90d
        sli:
          kind: ratio              # ratio of good_events / valid_events
          good_events: 'rate(http_requests_total{status!~"5.."}[5m])'
          valid_events: 'rate(http_requests_total{}[5m])'
        labels:
          tier: critical

      - name: latency-p95-500ms
        objective: 99
        window: 28d
        sli:
          kind: latency_threshold
          query: 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))'
          threshold_seconds: 0.5
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


SUPPORTED_WINDOWS = {"7d", "28d", "30d", "90d"}
SLI_KINDS = {"ratio", "latency_threshold"}

_WINDOW_MINUTES = {
    "7d": 7 * 24 * 60,
    "28d": 28 * 24 * 60,
    "30d": 30 * 24 * 60,
    "90d": 90 * 24 * 60,
}


@dataclass
class SLI:
    kind: Literal["ratio", "latency_threshold"]
    # ratio fields
    good_events: str | None = None
    valid_events: str | None = None
    # latency fields
    query: str | None = None
    threshold_seconds: float | None = None


@dataclass
class SLO:
    name: str
    objective: float
    window: str
    sli: SLI
    labels: dict[str, str] = field(default_factory=dict)

    def error_budget_pct(self) -> float:
        return round(100 - self.objective, 4)

    def error_budget_minutes(self) -> float:
        """Total error budget in minutes for the SLO window.

        Reports the absolute downtime budget on-callers think in. A 99.9%
        availability SLO over 30 days yields 43.2 minutes — that is the
        figure that ends up in incident reviews, not 0.1%.
        """
        return round(_WINDOW_MINUTES[self.window] * (100 - self.objective) / 100, 2)


@dataclass
class Spec:
    service: str
    owner: str
    slos: list[SLO]


def load(path: str | Path) -> Spec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return parse(raw, source=str(path))


def parse(raw: dict, *, source: str = "<inline>") -> Spec:
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: top-level YAML must be a mapping")
    for required in ("service", "owner", "slos"):
        if required not in raw:
            raise ValueError(f"{source}: missing top-level key '{required}'")
    if not isinstance(raw["slos"], list) or not raw["slos"]:
        raise ValueError(f"{source}: 'slos' must be a non-empty list")

    slos: list[SLO] = []
    seen_names: set[str] = set()
    for i, raw_slo in enumerate(raw["slos"]):
        slo = _parse_slo(raw_slo, index=i, source=source)
        if slo.name in seen_names:
            raise ValueError(f"{source}: duplicate SLO name '{slo.name}'")
        seen_names.add(slo.name)
        slos.append(slo)

    return Spec(service=str(raw["service"]), owner=str(raw["owner"]), slos=slos)


_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def _parse_slo(raw: dict, *, index: int, source: str) -> SLO:
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: SLO at index {index} must be a mapping")
    name = str(raw.get("name", "")).strip()
    if not _NAME_RE.match(name):
        raise ValueError(
            f"{source}: SLO name '{name}' must match {_NAME_RE.pattern}"
        )

    objective = raw.get("objective")
    if not isinstance(objective, (int, float)) or not (0 < objective <= 100):
        raise ValueError(f"{source}: SLO '{name}' objective must be a number in (0, 100]")

    window = str(raw.get("window", ""))
    if window not in SUPPORTED_WINDOWS:
        raise ValueError(
            f"{source}: SLO '{name}' window '{window}' must be one of {sorted(SUPPORTED_WINDOWS)}"
        )

    sli_raw = raw.get("sli")
    if not isinstance(sli_raw, dict):
        raise ValueError(f"{source}: SLO '{name}' missing 'sli' mapping")
    kind = sli_raw.get("kind")
    if kind not in SLI_KINDS:
        raise ValueError(f"{source}: SLO '{name}' sli.kind must be one of {sorted(SLI_KINDS)}")

    if kind == "ratio":
        good = sli_raw.get("good_events")
        valid = sli_raw.get("valid_events")
        if not (isinstance(good, str) and isinstance(valid, str)):
            raise ValueError(
                f"{source}: SLO '{name}' ratio SLI requires 'good_events' and 'valid_events' as PromQL strings"
            )
        sli = SLI(kind="ratio", good_events=good, valid_events=valid)
    else:
        query = sli_raw.get("query")
        threshold = sli_raw.get("threshold_seconds")
        if not isinstance(query, str):
            raise ValueError(
                f"{source}: SLO '{name}' latency_threshold requires 'query' (PromQL string)"
            )
        if not isinstance(threshold, (int, float)) or threshold <= 0:
            raise ValueError(
                f"{source}: SLO '{name}' latency_threshold requires 'threshold_seconds' > 0"
            )
        sli = SLI(kind="latency_threshold", query=query, threshold_seconds=float(threshold))

    labels = raw.get("labels") or {}
    if not isinstance(labels, dict):
        raise ValueError(f"{source}: SLO '{name}' labels must be a mapping if provided")

    return SLO(
        name=name,
        objective=float(objective),
        window=window,
        sli=sli,
        labels={str(k): str(v) for k, v in labels.items()},
    )
