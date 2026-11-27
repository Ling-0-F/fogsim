"""Restoration checks use small synthetic archives, never historical evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location("restore_sources", Path(__file__).resolve().parents[2] / "tools/restore_sources.py")
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    sources = tmp_path / "sources"
    sources.mkdir()
    source = sources / "renamed-source.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("original/one.txt", b"one")
        z.writestr("original/two.txt", b"two")
    def record(data):
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    doc = {"format": "fogsim.source-index", "schema_version": 1,
           "sources": [{"id": "s", "filename": "source.zip", **record(source.read_bytes())}],
           "entries": [{"path": f"history/{name}.txt", "group": "history", "source_id": "s",
                        "member": f"original/{name}.txt", **record(name.encode())} for name in ("one", "two")]}
    index = tmp_path / "index.json"
    index.write_text(json.dumps(doc))
    return root, sources, index, doc


def run(case, action="restore", dry_run=False, groups=None):
    root, sources, index, _ = case
    return restore.execute(index, root, groups or {"history"}, action, [sources], dry_run)


def change(case, mutate):
    doc = copy.deepcopy(case[3])
    mutate(doc)
    case[2].write_text(json.dumps(doc))


def test_exact_bytes_and_idempotency_with_renamed_source(case):
    assert run(case)["restored"] == 2
    assert (case[0] / "history/one.txt").read_bytes() == b"one"
    assert run(case)["restored"] == 0
    assert run(case, "verify")["complete"]


def test_missing_source_does_not_write(case):
    next(case[1].iterdir()).unlink()
    with pytest.raises(restore.RestoreError, match="missing or SHA-256"):
        run(case)
    assert not list(case[0].iterdir())


def test_source_digest_mismatch_does_not_write(case):
    path = next(case[1].iterdir())
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 1
    path.write_bytes(raw)
    with pytest.raises(restore.RestoreError, match="SHA-256"):
        run(case)
    assert not list(case[0].iterdir())


@pytest.mark.parametrize("field,value", [("path", "../escape"), ("member", "/absolute"), ("path", "C:\\escape")])
def test_path_escape_rejected(case, field, value):
    change(case, lambda d: d["entries"][0].update({field: value}))
    with pytest.raises(restore.RestoreError, match="unsafe"):
        run(case)
    assert not list(case[0].iterdir())


def test_existing_conflict_preserves_other_missing_target(case):
    target = case[0] / "history/two.txt"
    target.parent.mkdir()
    target.write_bytes(b"user edit")
    with pytest.raises(restore.RestoreError, match="refusing overwrite"):
        run(case)
    assert target.read_bytes() == b"user edit"
    assert not (case[0] / "history/one.txt").exists()


def test_symlink_parent_rejected(case):
    outside = case[0].parent / "outside"
    outside.mkdir()
    (case[0] / "history").symlink_to(outside, target_is_directory=True)
    with pytest.raises(restore.RestoreError, match="symbolic link"):
        run(case)
    assert not list(outside.iterdir())


def test_dry_run_checks_members_without_any_writes(case):
    assert run(case, dry_run=True)["validated_missing_members"] == 2
    assert not list(case[0].iterdir())


def test_member_digest_failure_has_no_partial_commit(case):
    change(case, lambda d: d["entries"][1].update(sha256="0" * 64))
    with pytest.raises(restore.RestoreError, match="digest differs"):
        run(case)
    assert not list(case[0].iterdir())


def test_raw_zip_and_group_selection(case):
    change(case, lambda d: d["entries"].append({"path": "rollback/source.zip", "group": "rollback",
                                              "source_id": "s", "member": None,
                                              "bytes": d["sources"][0]["bytes"], "sha256": d["sources"][0]["sha256"]}))
    assert run(case, groups={"rollback"})["restored"] == 1
    assert not (case[0] / "history").exists()
    assert (case[0] / "rollback/source.zip").read_bytes() == next(case[1].iterdir()).read_bytes()


def test_verify_missing_reports_incomplete_without_sources(case):
    assert not run(case, action="verify")["complete"]
    assert not list(case[0].iterdir())
