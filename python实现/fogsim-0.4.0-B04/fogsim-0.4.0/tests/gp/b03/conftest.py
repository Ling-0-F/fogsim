import json
import os
from pathlib import Path
import struct
import pytest


def raw(value):
    if type(value) is float:
        return {"binary64": struct.pack(">d", value).hex()}
    if isinstance(value, dict):
        return {str(k): raw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [raw(v) for v in value]
    return value


@pytest.fixture(scope="session")
def evidence_b03():
    rows = {}
    def record(group, row):
        rows.setdefault(group, []).append(raw(row))
    yield record
    if target := os.environ.get("FOGSIM_B03_EVIDENCE"):
        path = Path(target); path.mkdir(parents=True, exist_ok=True)
        for group, values in rows.items():
            (path / (group + ".jsonl")).write_text("".join(json.dumps(v, ensure_ascii=False,
                allow_nan=False) + "\n" for v in values), encoding="utf-8")
