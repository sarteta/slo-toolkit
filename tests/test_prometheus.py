from pathlib import Path

import yaml

from slo_toolkit import prometheus, spec as spec_module


EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "payments-api.yml"


def test_build_rules_has_two_groups_per_slo():
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    # 3 SLOs * 2 groups (recording + alerting) = 6 groups
    assert len(out["groups"]) == 6


def test_recording_rule_records_sli_value():
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    rec_group = next(g for g in out["groups"] if "recording" in g["name"])
    record_names = [r["record"] for r in rec_group["rules"]]
    assert any("slo:sli_value:availability" in n for n in record_names)


def test_alert_rule_emits_fast_and_slow_burn():
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    alert_group = next(g for g in out["groups"] if "alerting" in g["name"])
    alert_names = [r["alert"] for r in alert_group["rules"]]
    assert any("FastBurn" in n for n in alert_names)
    assert any("SlowBurn" in n for n in alert_names)


def test_yaml_output_is_parseable():
    s = spec_module.load(EXAMPLE)
    text = prometheus.render_yaml(s)
    parsed = yaml.safe_load(text)
    assert "groups" in parsed
    assert isinstance(parsed["groups"], list)


def test_severity_labels_present():
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    for g in out["groups"]:
        if "alerting" in g["name"]:
            severities = {r["labels"]["severity"] for r in g["rules"]}
            assert {"page", "ticket"}.issubset(severities)


def test_burn_rate_thresholds_match_google_workbook():
    """The Google SRE workbook chapter on alerting recommends burn-rate
    thresholds of 14.4 (fast, 5m+1h windows) and 6 (slow, 30m+6h windows).
    Encoding this as a regression test so the constants don't drift
    accidentally."""
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    alert_group = next(g for g in out["groups"] if "alerting" in g["name"])
    fast_alert = next(r for r in alert_group["rules"] if "FastBurn" in r["alert"])
    slow_alert = next(r for r in alert_group["rules"] if "SlowBurn" in r["alert"])
    assert "14.4" in fast_alert["expr"]
    assert "> 6" in slow_alert["expr"]


def test_labels_inherited_from_spec():
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    rec_group = next(g for g in out["groups"] if "availability:recording" in g["name"])
    labels = rec_group["rules"][0]["labels"]
    # service + owner from top-level
    assert labels["service"] == "payments-api"
    assert labels["owner"] == "platform-team"
    # tier comes from the SLO itself
    assert labels.get("tier") == "critical"


def test_record_names_replace_hyphens_with_underscores():
    """Prometheus rule names must match [a-zA-Z_:][a-zA-Z0-9_:]* — hyphens are
    illegal. SLO names with hyphens (latency-p95-500ms) must map to
    slo:sli_value:latency_p95_500ms in the emitted rules."""
    import re
    s = spec_module.load(EXAMPLE)
    out = prometheus.build_rules(s)
    # Slugs that contain hyphens in the YAML
    hyphen_slos = [slo.name for slo in s.slos if "-" in slo.name]
    assert hyphen_slos, "test fixture must include at least one hyphenated SLO name"

    record_pattern = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
    for group in out["groups"]:
        for rule in group["rules"]:
            name = rule.get("record") or rule.get("alert")
            assert record_pattern.match(name), (
                f"rule name {name!r} fails Prometheus naming regex"
            )
            # Specifically: no hyphens
            assert "-" not in name, f"rule name {name!r} still has hyphens"
