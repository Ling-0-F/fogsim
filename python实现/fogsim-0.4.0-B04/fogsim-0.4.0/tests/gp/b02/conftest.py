import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def evidence_b02():
    rows = {}

    def record(group, value):
        rows.setdefault(group, []).append(value)

    yield record
    if target := os.environ.get("FOGSIM_B02_EVIDENCE"):
        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        for group, values in rows.items():
            (directory / f"{group}.jsonl").write_text("".join(
                json.dumps(value, sort_keys=True, allow_nan=False) + "\n" for value in values))
