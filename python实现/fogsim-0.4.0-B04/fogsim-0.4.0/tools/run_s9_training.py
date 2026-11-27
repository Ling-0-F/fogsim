"""Default to preflight; --execute explicitly runs the editable training config."""
import argparse
from pathlib import Path
from fogsim.training.cli import main as training_main

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "configs/training/large-dual-template.json"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true", help="run training after displaying budget and retention")
    args = parser.parse_args(argv)
    return training_main(["train" if args.execute else "validate", "--config", args.config, "--output", args.output])


if __name__ == "__main__":
    raise SystemExit(main())
