"""Command-line entry point: `rg <command>`."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rg")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="load and validate every config")
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        from rg.config import load_arms, load_gate, load_models, load_topology

        load_topology(), load_gate(), load_arms(), load_models()
        print("configs OK")


if __name__ == "__main__":
    main()
