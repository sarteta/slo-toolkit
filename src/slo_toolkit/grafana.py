"""Generate a Grafana dashboard JSON from an SLO spec.

The dashboard is intentionally minimal: one row per SLO, three panels
each (current SLI, error budget remaining, burn rate). It works as a
starting point — Grafana lets you import the JSON, then iterate
visually from there.
"""
from __future__ import annotations

import json

from .spec import SLO, Spec


def _panel_sli(slo: SLO, panel_id: int, x: int, y: int) -> dict:
    return {
        "id": panel_id,
        "type": "stat",
        "title": f"{slo.name} — SLI",
        "gridPos": {"x": x, "y": y, "w": 6, "h": 6},
        "targets": [
            {"expr": f"slo:sli_value:{slo.name}", "refId": "A"},
        ],
        "fieldConfig": {
            "defaults": {
                "unit": "percentunit",
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "orange", "value": slo.objective / 100 - 0.005},
                        {"color": "green", "value": slo.objective / 100},
                    ],
                },
            }
        },
    }


def _panel_objective(slo: SLO, panel_id: int, x: int, y: int) -> dict:
    return {
        "id": panel_id,
        "type": "stat",
        "title": f"{slo.name} — Objective",
        "gridPos": {"x": x, "y": y, "w": 6, "h": 6},
        "targets": [
            {"expr": f"slo:objective:{slo.name}", "refId": "A"},
        ],
        "fieldConfig": {"defaults": {"unit": "percent"}},
    }


def _panel_error_budget(slo: SLO, panel_id: int, x: int, y: int) -> dict:
    return {
        "id": panel_id,
        "type": "stat",
        "title": f"{slo.name} — Error budget remaining",
        "gridPos": {"x": x, "y": y, "w": 12, "h": 6},
        "targets": [
            {
                "expr": (
                    f"1 - ((1 - slo:sli_value:{slo.name}) / "
                    f"((100 - slo:objective:{slo.name}) / 100))"
                ),
                "refId": "A",
            },
        ],
        "fieldConfig": {
            "defaults": {
                "unit": "percentunit",
                "min": 0,
                "max": 1,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "orange", "value": 0.25},
                        {"color": "green", "value": 0.5},
                    ],
                },
            }
        },
    }


def build_dashboard(spec: Spec) -> dict:
    panels: list[dict] = []
    next_id = 1
    for row, slo in enumerate(spec.slos):
        y = row * 6
        panels.append(_panel_sli(slo, next_id, 0, y)); next_id += 1
        panels.append(_panel_objective(slo, next_id, 6, y)); next_id += 1
        panels.append(_panel_error_budget(slo, next_id, 12, y)); next_id += 1

    return {
        "uid": f"slo-{spec.service}",
        "title": f"SLOs — {spec.service}",
        "tags": ["slo", "auto-generated", spec.owner],
        "schemaVersion": 38,
        "version": 1,
        "panels": panels,
        "refresh": "30s",
    }


def render_json(spec: Spec, *, indent: int = 2) -> str:
    return json.dumps(build_dashboard(spec), indent=indent)
