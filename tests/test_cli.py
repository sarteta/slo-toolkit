from pathlib import Path

from slo_toolkit.cli import main

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "payments-api.yml"


def test_cli_writes_both_files(tmp_path):
    out_dir = tmp_path / "build"
    rc = main(["--spec", str(EXAMPLE), "--out-dir", str(out_dir)])
    assert rc == 0
    assert (out_dir / "payments-api-slos.yml").exists()
    assert (out_dir / "payments-api-dashboard.json").exists()


def test_cli_prom_only(tmp_path):
    out_dir = tmp_path / "build"
    rc = main(["--spec", str(EXAMPLE), "--out-dir", str(out_dir), "--prom-only"])
    assert rc == 0
    assert (out_dir / "payments-api-slos.yml").exists()
    assert not (out_dir / "payments-api-dashboard.json").exists()


def test_cli_grafana_only(tmp_path):
    out_dir = tmp_path / "build"
    rc = main(["--spec", str(EXAMPLE), "--out-dir", str(out_dir), "--grafana-only"])
    assert rc == 0
    assert not (out_dir / "payments-api-slos.yml").exists()
    assert (out_dir / "payments-api-dashboard.json").exists()


def test_cli_returns_2_on_bad_spec(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("not: a: valid: spec", encoding="utf-8")
    rc = main(["--spec", str(bad), "--out-dir", str(tmp_path / "out")])
    assert rc == 2
