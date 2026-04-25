import json
from pathlib import Path

import pytest

from slo_toolkit import grafana, spec as spec_module


EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "payments-api.yml"


def test_dashboard_has_three_panels_per_slo():
    s = spec_module.load(EXAMPLE)
    dash = grafana.build_dashboard(s)
    # 3 SLOs * 3 panels each = 9 panels
    assert len(dash["panels"]) == 9


def test_dashboard_uid_includes_service():
    s = spec_module.load(EXAMPLE)
    dash = grafana.build_dashboard(s)
    assert dash["uid"] == "slo-payments-api"


def test_render_json_is_valid():
    s = spec_module.load(EXAMPLE)
    out = grafana.render_json(s)
    parsed = json.loads(out)
    assert parsed["title"] == "SLOs -- payments-api"


def test_panels_have_unique_ids():
    s = spec_module.load(EXAMPLE)
    dash = grafana.build_dashboard(s)
    ids = [p["id"] for p in dash["panels"]]
    assert len(ids) == len(set(ids)), "panel ids must be unique within a dashboard"


def test_sli_panel_thresholds_reflect_objective():
    s = spec_module.load(EXAMPLE)
    dash = grafana.build_dashboard(s)
    # availability SLO is 99.9 -> green threshold should be 0.999
    avail_panel = next(p for p in dash["panels"] if "availability" in p["title"] and "SLI" in p["title"])
    steps = avail_panel["fieldConfig"]["defaults"]["thresholds"]["steps"]
    green_step = next(s for s in steps if s["color"] == "green")
    # Float arithmetic: 99.9 / 100 isn't exactly 0.999 in IEEE 754.
    assert green_step["value"] == pytest.approx(0.999)
