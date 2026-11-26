"""Compare complete GPU runs trial by trial, including history, validation and held-out results."""

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path


def compare(left, right, out):
    runs = [json.loads((path / "search/run.json").read_text()) for path in (left, right)]
    records = [{r["trial"]: r for r in run["trials"]} for run in runs]
    expected = set(range(1, 31))
    if any(run["count"] != len(expected) for run in runs) or any(
        set(group) != expected for group in records
    ):
        raise ValueError("Expected trials 1 through 30 on both devices")
    rows = []
    for trial in sorted(expected):
        prefix = f"small-1-trial-{trial:02d}"
        row = dict(trial=trial, evolution_seed=50000 + trial)
        for ext, key in ((".json", "history_and_validation_sha256"), (".csv", "heldout_csv_sha256")):
            hashes = []
            for root, trials in zip((left, right), records, strict=True):
                path = root / "search/trials" / prefix / (prefix + ext)
                digest = sha256(path.read_bytes()).hexdigest()
                if digest != trials[trial]["sha256"][ext]:
                    raise ValueError(f"Checksum mismatch in {path}")
                hashes.append(digest)
            if hashes[0] != hashes[1]:
                raise ValueError(f"The two devices differ for {prefix}{ext}")
            row[key] = hashes[0]
        rows.append(row)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cross-device.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    devices = [
        dict(
            engine=r.get("engine", "musa"),
            device=r.get("gpu_name", "MTT S4000"),
            lanes=r["lanes"],
            processes=r["parallel"],
            unique_train=r["unique_train"],
            wall_s=r["wall_s"],
        )
        for r in runs
    ]
    result = dict(
        devices=devices,
        identical_history_and_validation_files=len(rows),
        identical_test_files=len(rows),
        matched_heldout_rows=30 * len(rows),
        first_wall_over_second=devices[0]["wall_s"] / devices[1]["wall_s"],
    )
    (out / "cross-device.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.first, args.second, args.out), indent=2))
