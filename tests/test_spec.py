from pathlib import Path

import pytest

from slo_toolkit import spec as spec_module


EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "payments-api.yml"


def test_load_example_spec():
    s = spec_module.load(EXAMPLE)
    assert s.service == "payments-api"
    assert s.owner == "platform-team"
    assert len(s.slos) == 3


def test_error_budget_pct():
    s = spec_module.load(EXAMPLE)
    avail = next(slo for slo in s.slos if slo.name == "availability")
    assert avail.error_budget_pct() == pytest.approx(0.1)


def test_invalid_window_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n  - name: avail_x\n    objective: 99\n    window: 3d\n"
        "    sli:\n      kind: ratio\n      good_events: 'rate(x[5m])'\n      valid_events: 'rate(x[5m])'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="window"):
        spec_module.load(bad)


def test_invalid_objective_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n  - name: avail_x\n    objective: 200\n    window: 7d\n"
        "    sli:\n      kind: ratio\n      good_events: 'rate(x[5m])'\n      valid_events: 'rate(x[5m])'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="objective"):
        spec_module.load(bad)


def test_invalid_name_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n  - name: 'BadName With Spaces'\n    objective: 99\n    window: 7d\n"
        "    sli:\n      kind: ratio\n      good_events: 'rate(x[5m])'\n      valid_events: 'rate(x[5m])'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must match"):
        spec_module.load(bad)


def test_duplicate_name_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n"
        "  - name: avail_x\n    objective: 99\n    window: 7d\n"
        "    sli:\n      kind: ratio\n      good_events: 'a'\n      valid_events: 'b'\n"
        "  - name: avail_x\n    objective: 99\n    window: 7d\n"
        "    sli:\n      kind: ratio\n      good_events: 'a'\n      valid_events: 'b'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        spec_module.load(bad)


def test_unknown_sli_kind_raises(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n  - name: avail_x\n    objective: 99\n    window: 7d\n"
        "    sli:\n      kind: nonsense\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sli.kind"):
        spec_module.load(bad)


def test_latency_requires_threshold(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "service: a\nowner: b\nslos:\n  - name: lat_x\n    objective: 99\n    window: 7d\n"
        "    sli:\n      kind: latency_threshold\n      query: 'q'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="threshold_seconds"):
        spec_module.load(bad)
