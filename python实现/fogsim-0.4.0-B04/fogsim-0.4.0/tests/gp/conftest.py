"""Optional raw evidence output; assertions run identically without this option."""
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def evidence():
    rows = {}

    def record(group, row):
        rows.setdefault(group, []).append(row)

    yield record
    target = os.environ.get("FOGSIM_B01_EVIDENCE")
    if target:
        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        for group, values in rows.items():
            (directory / f"{group}.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in values),
                encoding="utf-8")
