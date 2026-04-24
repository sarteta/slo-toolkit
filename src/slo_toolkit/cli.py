"""CLI: generate Prometheus rules and Grafana dashboards from an SLO YAML.

    slo-toolkit --spec slos.yml --out-dir build/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import grafana, prometheus, spec as spec_module


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="slo-toolkit")
    ap.add_argument("--spec", required=True, help="Path to YAML SLO spec")
    ap.add_argument("--out-dir", default="build", help="Output directory")
    ap.add_argument(
        "--prom-only",
        action="store_true",
        help="Only emit the Prometheus rules file (skip Grafana JSON)",
    )
    ap.add_argument(
        "--grafana-only",
        action="store_true",
        help="Only emit the Grafana dashboard JSON (skip Prometheus rules)",
    )
    args = ap.parse_args(argv)

    try:
        s = spec_module.load(args.spec)
    except Exception as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not args.grafana_only:
        rules_path = out / f"{s.service}-slos.yml"
        rules_path.write_text(prometheus.render_yaml(s), encoding="utf-8")
        print(f"wrote {rules_path}")

    if not args.prom_only:
        dash_path = out / f"{s.service}-dashboard.json"
        dash_path.write_text(grafana.render_json(s), encoding="utf-8")
        print(f"wrote {dash_path}")

    print(f"service={s.service} slos={len(s.slos)} owner={s.owner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
