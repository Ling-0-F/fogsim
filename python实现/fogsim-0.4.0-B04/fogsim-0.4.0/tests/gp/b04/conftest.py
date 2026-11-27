import json
import os
from pathlib import Path
import pytest
from ..b03.conftest import raw

@pytest.fixture(scope="session")
def evidence_b04():
    rows = {}
    def record(group, value): rows.setdefault(group, []).append(raw(value))
    yield record
    if destination := os.environ.get("FOGSIM_B04_EVIDENCE"):
        out = Path(destination); out.mkdir(parents=True, exist_ok=True)
        for name, values in rows.items():
            (out / (name + ".jsonl")).write_text("".join(json.dumps(v, ensure_ascii=True, allow_nan=False) + "\n" for v in values))
