"""Independently unpack a release ZIP, verify all hashes, recompile and run 14 cases."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("archive", type=Path); p.add_argument("--java", required=True)
    p.add_argument("--output", type=Path, default=ROOT / "outputs/package-smoke-v2.json")
    a = p.parse_args(); archive = a.archive.resolve()
    with tempfile.TemporaryDirectory(prefix="package-check-", dir=ROOT.parent) as folder:
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if Path(name).is_absolute() or ".." in Path(name).parts: raise ValueError("unsafe ZIP path")
            assert z.testzip() is None
            z.extractall(folder)
        roots = [x for x in Path(folder).iterdir() if x.is_dir()]
        assert len(roots) == 1
        root = roots[0]
        manifest = json.loads((root / "RELEASE-FILES.json").read_text())
        for relative, expected in manifest.items():
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
        script = r'''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(root/'src'),str(root/'tools')]
import fogsim,run_fixed_parity,java_support
assert Path(fogsim.__file__).resolve().is_relative_to(root)
assert java_support.ORIGINAL.resolve().is_relative_to(root)
summary=run_fixed_parity.run_suite(root/'outputs/package-check',sys.argv[2])
build=json.loads((root/'outputs/package-check/build/build-manifest.json').read_text())
import os
for part in build['runtime_classpath'].split(os.pathsep):assert Path(part).resolve().is_relative_to(root)
assert summary['passed'] and len(summary['cases'])==14
print(json.dumps({'passed':True,'version':fogsim.__version__,'cases':summary['cases'],
 'imported_module':fogsim.__file__,'original_java':str(java_support.ORIGINAL),
 'all_runtime_classpath_inside_package':True,'java_build_fingerprint':build['fingerprint']}))
'''
        command = [sys.executable, "-I", "-c", script, str(root), str(Path(a.java).resolve())]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120)
        if result.returncode: raise RuntimeError(result.stdout + result.stderr)
        report = dict(json.loads(result.stdout), archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                      checked_file_count=len(manifest), isolation="Python -I, fresh extraction, fresh Java compilation")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "archive_sha256":report["archive_sha256"],
                      "checked_file_count":report["checked_file_count"]}))


if __name__ == "__main__": main()
