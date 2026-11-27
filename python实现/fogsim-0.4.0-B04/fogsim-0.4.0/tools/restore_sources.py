"""Restore indexed, hash-pinned source files without changing existing content.

Uses only Python's standard library. No network access, ZIP extractall, or
filename-only trust. Run --help from an independently extracted distribution.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("java", "history", "rollback")


class RestoreError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise RestoreError(f"unsafe relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise RestoreError(f"unsafe relative path: {value!r}")
    return path


def validate_record(record):
    if type(record.get("bytes")) is not int or record["bytes"] < 0:
        raise RestoreError("invalid byte count")
    sha = record.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise RestoreError("invalid SHA-256")


def load_index(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") != "fogsim.source-index" or doc.get("schema_version") != 1:
        raise RestoreError("unsupported source index")
    sources = {}
    for source in doc["sources"]:
        validate_record(source)
        if source["id"] in sources:
            raise RestoreError("duplicate source id")
        sources[source["id"]] = source
    targets = set()
    for entry in doc["entries"]:
        validate_record(entry)
        target = str(safe_relative(entry["path"]))
        if target in targets:
            raise RestoreError(f"duplicate target: {target}")
        targets.add(target)
        if entry["group"] not in GROUPS or entry["source_id"] not in sources:
            raise RestoreError("unknown group/source")
        if entry["member"] is not None:
            safe_relative(entry["member"])
        elif any(entry[k] != sources[entry["source_id"]][k] for k in ("bytes", "sha256")):
            raise RestoreError("raw source digest differs from target")
    return doc, sources


def target_path(root, relative):
    path = root.joinpath(*safe_relative(relative).parts)
    current = root
    for part in safe_relative(relative).parts:
        current = current / part
        if current.is_symlink():
            raise RestoreError(f"symbolic link in target path: {relative}")
        if current != path and current.exists() and not current.is_dir():
            raise RestoreError(f"non-directory ancestor: {relative}")
    if path.exists() and not path.is_file():
        raise RestoreError(f"target is not a regular file: {relative}")
    return path


def matches(path, record):
    return path.is_file() and path.stat().st_size == record["bytes"] and digest(path) == record["sha256"]


def resolve_sources(sources, needed, directories):
    # A caller explicitly supplies local directories; only their direct ZIP
    # children are inspected. Renaming a source does not change its identity.
    candidates = []
    for directory in directories:
        directory = Path(directory).resolve()
        if not directory.is_dir():
            raise RestoreError(f"source directory missing: {directory}")
        candidates.extend(p for p in sorted(directory.iterdir()) if p.is_file() and p.suffix.lower() == ".zip")
    hashes = {}
    result = {}
    for sid in sorted(needed):
        record = sources[sid]
        for candidate in candidates:
            if candidate.stat().st_size != record["bytes"]:
                continue
            if candidate not in hashes:
                hashes[candidate] = digest(candidate)
            if hashes[candidate] == record["sha256"]:
                result[sid] = candidate
                break
        else:
            raise RestoreError(f"missing or SHA-256-mismatched source: {record['filename']} "
                               f"(bytes={record['bytes']}, sha256={record['sha256']})")
    return result


def execute(index, root, groups, action, directories=(), dry_run=False):
    doc, sources = load_index(index)
    root = Path(root).resolve()
    if not root.is_dir():
        raise RestoreError(f"project root missing: {root}")
    selected = [e for e in doc["entries"] if e["group"] in groups]
    missing, existing, conflicts = [], [], []
    for entry in selected:
        target = target_path(root, entry["path"])
        if not target.exists():
            missing.append(entry)
        elif matches(target, entry):
            existing.append(entry)
        else:
            conflicts.append(entry["path"])
    if conflicts:
        raise RestoreError("existing content differs; refusing overwrite: " + ", ".join(conflicts[:10]))
    report = dict(format="fogsim.source-restore", schema_version=1, action=action,
                  groups=sorted(groups), selected=len(selected), existing=len(existing),
                  missing=len(missing), restored=0, dry_run=dry_run,
                  index_sha256=digest(index), complete=not missing)
    if action == "verify" or not missing:
        return report
    located = resolve_sources(sources, {e["source_id"] for e in missing}, directories)
    # Validate every selected member before the first write. Reject duplicate
    # names and symlinks rather than trusting ZipFile.read's duplicate choice.
    with ExitStack() as stack:
        archives = {}
        members = {}
        for sid in located:
            if any(e["source_id"] == sid and e["member"] is not None for e in missing):
                archive = stack.enter_context(zipfile.ZipFile(located[sid]))
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise RestoreError(f"duplicate ZIP member in {sid}")
                archives[sid] = archive
        for entry in missing:
            member = entry["member"]
            if member is not None:
                archive = archives[entry["source_id"]]
                try:
                    info = archive.getinfo(member)
                except KeyError as exc:
                    raise RestoreError(f"missing ZIP member: {member}") from exc
                if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.file_size != entry["bytes"]:
                    raise RestoreError(f"invalid ZIP member: {member}")
                members[entry["path"]] = info
        # Stage and checksum all data before committing any target. Dry-run
        # fully reads members (including CRC verification), without writing.
        staging = None if dry_run else Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".source-restore-", dir=root)))
        for number, entry in enumerate(missing):
            source = (archives[entry["source_id"]].open(members[entry["path"]])
                      if entry["member"] is not None else located[entry["source_id"]].open("rb"))
            h = hashlib.sha256()
            count = 0
            with source:
                target_stream = None if dry_run else stack.enter_context((staging / str(number)).open("wb"))
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    h.update(chunk)
                    count += len(chunk)
                    if target_stream is not None:
                        target_stream.write(chunk)
                if target_stream is not None:
                    target_stream.close()
            if count != entry["bytes"] or h.hexdigest() != entry["sha256"]:
                raise RestoreError(f"source member digest differs: {entry['path']}")
        if not dry_run:
            for number, entry in enumerate(missing):
                target = target_path(root, entry["path"])
                if target.exists():
                    if not matches(target, entry):
                        raise RestoreError(f"target changed during restoration: {entry['path']}")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / str(number), target)
                report["restored"] += 1
            report["complete"] = True
    report["sources_verified"] = sorted(located)
    report["validated_missing_members"] = len(missing)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "restore"))
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--index", type=Path, default=ROOT / "SOURCE-INDEX.json")
    parser.add_argument("--group", action="append", choices=(*GROUPS, "all"))
    parser.add_argument("--source-dir", type=Path, action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    groups = set(args.group or ["all"])
    if "all" in groups:
        groups = set(GROUPS)
    try:
        result = execute(args.index, args.project_root, groups, args.action, args.source_dir, args.dry_run)
        code = 0 if result["complete"] or args.dry_run else 1
    except (RestoreError, OSError, KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        result = dict(format="fogsim.source-restore", complete=False, error=f"{type(exc).__name__}: {exc}")
        code = 2
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
