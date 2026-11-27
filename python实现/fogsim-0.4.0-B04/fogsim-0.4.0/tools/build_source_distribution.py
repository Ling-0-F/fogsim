"""Build/verify the B01 source-indexed distribution, leaving old manifests intact."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "SOURCE-DISTRIBUTION-FILES.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    errors = []
    from restore_sources import safe_relative
    for rel, expected in manifest["files"].items():
        target = root.joinpath(*safe_relative(rel).parts)
        if target.is_symlink() or not target.is_file():
            errors.append(rel)
            continue
        data = target.read_bytes()
        if len(data) != expected["bytes"] or digest(data) != expected["sha256"]:
            errors.append(rel)
    return dict(format="fogsim.source-distribution-integrity", passed=not errors,
                manifest_files_checked=len(manifest["files"]), mismatches=errors)


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError("package output must be outside the project root")
    if output.exists():
        raise ValueError("refusing to replace an existing package")
    index = json.loads((root / "SOURCE-INDEX.json").read_text(encoding="utf-8"))
    if any((root / e["path"]).exists() for e in index["entries"]):
        raise ValueError("build from the unhydrated source-indexed tree, not a restored/test-mutated copy")
    removed = json.loads((root / "development/source-dedup/removed-generated-files.json").read_text())["files"]
    if any((root / e["path"]).exists() for e in removed):
        raise ValueError("excluded generated files reappeared")
    acceptance = json.loads((root / "outputs/step9/B01/acceptance.json").read_text())
    from fogsim.training.protocols import identity
    package_root = root / "src/fogsim"
    source_files = {p.relative_to(package_root).as_posix(): digest(p.read_bytes())
                    for p in sorted(package_root.rglob("*.py"))}
    source = dict(source_id=identity("implementation-source", source_files), source_files=source_files)
    if not acceptance["acceptance_passed"] or acceptance["source"] != source:
        raise ValueError("production source no longer matches accepted B01")
    paths = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"unexpected symbolic link: {path}")
        if not path.is_file() or path.name == MANIFEST:
            continue
        rel = path.relative_to(root)
        if any(x in ("__pycache__", ".pytest_cache", ".git") for x in rel.parts) or path.suffix == ".pyc":
            continue
        paths.append(path)
    files = {p.relative_to(root).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in paths}
    manifest_path = root / MANIFEST
    manifest_path.write_text(json.dumps(dict(format="fogsim.source-distribution-files", schema_version=1,
        distribution="B01-source-dedup", original_package=index["original_package"], files=files),
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths.append(manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        directory = zipfile.ZipInfo("fogsim-0.4.0/", (2026, 11, 14, 12, 0, 0))
        directory.external_attr = (0o40755 << 16) | 0x10
        z.writestr(directory, "")
        for path in sorted(paths):
            info = zipfile.ZipInfo("fogsim-0.4.0/" + path.relative_to(root).as_posix(), (2026, 11, 14, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            z.writestr(info, path.read_bytes(), compresslevel=6)
    with zipfile.ZipFile(output) as z:
        if z.testzip():
            raise ValueError("ZIP CRC verification failed")
    return dict(package=output.name, bytes=output.stat().st_size, sha256=digest(output.read_bytes()),
                top_directory="fogsim-0.4.0/", files=len(paths), crc_passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "build" and args.output is None:
        parser.error("build requires --output")
    result = build(args.root, args.output) if args.action == "build" else verify(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
