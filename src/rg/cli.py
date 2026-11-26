"""Command-line entry point.

  rg validate                                   load and validate every config
  rg run --arm A3 --model llama3.2-3b --seeds 0-4 [--scenarios A1-...,B2-...] [--workers 2]
         [--catalogue adaptive]                 supplementary, post hoc scenario file
  rg analyze                                    regenerate every table and figure
  rg irr export|score                           inter-rater labelling sheet / Cohen's kappa
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="load and validate every config")
    r = sub.add_parser("run", help="run one (arm, model) cell")
    r.add_argument("--arm", required=True, help="arm name, or comma-separated list")
    r.add_argument("--model", default="none")
    r.add_argument("--seeds", default="0-14")
    r.add_argument("--scenarios", default=None)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--catalogue", default="main",
                   help="main (frozen, pre-registered) or a supplementary catalogue, e.g. adaptive")
    sub.add_parser("analyze", help="regenerate tables and figures from results/raw")
    irr = sub.add_parser("irr", help="inter-rater agreement on the label set")
    irr.add_argument("action", choices=["export", "score"])
    args = parser.parse_args(argv)

    if args.cmd == "validate":
        from rg.config import (
            catalogue_sha,
            load_arms,
            load_gate,
            load_models,
            load_scenarios,
            load_topology,
        )

        load_topology(), load_gate(), load_arms(), load_models()
        print(f"configs OK; {len(load_scenarios())} scenarios; catalogue sha256 {catalogue_sha()}")
    elif args.cmd == "run":
        from rg.harness.runner import parse_seeds, run_cell

        scen = args.scenarios.split(",") if args.scenarios else None
        for arm in args.arm.split(","):
            p = run_cell(arm, args.model, parse_seeds(args.seeds), scen, args.workers,
                         catalogue=args.catalogue)
            print(f"wrote {p}")
    elif args.cmd == "analyze":
        from rg.analysis.report import main as report

        report()
    elif args.cmd == "irr":
        from rg.analysis.irr import export, score

        export() if args.action == "export" else score()


if __name__ == "__main__":
    main()
