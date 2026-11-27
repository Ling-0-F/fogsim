"""S9 canonical encoding. Immutable snapshots store canonical JSON, never engines."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import os
from fogsim.errors import InputError
from fogsim.replay.loader import read_replay_json

IMPLEMENTATION = "fogsim-training-evaluation-B01-v1"
POLICY = "all_success_feasible_v1"
SEMANTICS = {
    "language_version": "fogsim-gp-lisp-v1",
    "feature_semantics_version": "fogsim-features-java-v1",
    "numeric_semantics_version": "fogsim-gp-f64-dual-zero-v1",
    "selection_policy_version": "fogsim-selection-java-v1",
    "identity_encoding_version": "fogsim-rule-identity-v1",
}


def canonical(value):
    try:
        # ensure_ascii=False: UTF-8, no normalization; reject unpaired surrogates.
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
        result.encode("utf-8")
        return result
    except (ValueError, TypeError, UnicodeError) as exc:
        raise InputError(f"invalid training JSON: {exc}") from exc


def identity(domain, payload):
    return "sha256:" + sha256((f"fogsim.training.{domain}.v1\n" + canonical(payload)).encode()).hexdigest()


def content_sha(data):
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    document: str

    def to_dict(self):
        return json.loads(self.document)


def read_json(path):
    try:
        return read_replay_json(Path(path))
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc


def write_json(path, data):
    from fogsim.io import write_json_atomic
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, data)


def empty_output(path):
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise InputError(f"output must be absent or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_provenance():
    root = Path(__file__).resolve().parents[1]
    files = {p.relative_to(root).as_posix(): content_sha(p.read_bytes()) for p in sorted(root.rglob("*.py"))}
    return dict(source_id=identity("implementation-source", files), source_files=files)


def append_jsonl(path, value):
    path = Path(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path):
    """Only committed LF-terminated rows; report, never treat a tail as committed."""
    data = Path(path).read_bytes()
    lines = data.splitlines(keepends=True)
    incomplete = bool(lines and not lines[-1].endswith(b"\n"))
    rows = [json.loads(line) for line in (lines[:-1] if incomplete else lines)]
    return dict(rows=rows, interrupted_tail=incomplete,
                tail_bytes=len(lines[-1]) if incomplete else 0)
