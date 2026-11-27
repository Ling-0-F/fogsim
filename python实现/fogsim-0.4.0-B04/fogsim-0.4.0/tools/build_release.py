"""Package source, fixtures, evidence and selected original Java references."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
import tomllib

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,help="alternate ZIP path, e.g. when an existing archive is open")
    args=parser.parse_args(argv)
    version=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    prefix=f"fogsim-{version}"
    files=[ROOT/name for name in ("README.md","pyproject.toml",".gitignore","CHANGES-FROM-0.2.0a1.patch")]
    for folder in ("src","tests","tools","configs","data","docs","references/design","examples","dax"):
        files.extend(p for p in (ROOT/folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and not any(x.endswith(".egg-info") for x in p.parts))
    files.extend(p for p in (ROOT/"outputs").glob("*") if p.is_file() and p.suffix in (".json",".xml",".txt"))
    for folder in ("java_oracle","parity","v0.1","development","v2","issues","history-0.2.0a1"):
        files.extend(p for p in (ROOT/"outputs"/folder).rglob("*") if p.is_file() and "classes" not in p.parts)
    jroot=ROOT/"references/java/Fog-Computing-multiDeviceDebug"
    files.append(ROOT/"references/INPUT-SHA256.json")
    files.append(jroot/".idea/misc.xml")
    files.extend(p for p in (jroot/"src").rglob("*") if p.is_file() and p.suffix != ".class" and p.name != ".DS_Store")
    files.extend(p for p in (jroot/"libraries").glob("*") if p.is_file() and "javadoc" not in p.name
                 and (p.suffix==".jar" or p.name=="README"))
    files.extend(p for pattern in ("CHANGES-STEP*.patch", "STEP*-FILES.json") for p in ROOT.glob(pattern) if p.is_file())
    for folder in ("step1","step2","step3","step4","step5","step5-final","step6","step7","history-step6-before-v01","final","history-step7-v01"):
        files.extend(p for p in (ROOT/"outputs"/folder).rglob("*") if p.is_file() and
                     "classes" not in p.parts and "tmp" not in p.parts and not any(x.startswith(".") for x in p.relative_to(ROOT).parts))
    if (ROOT/"CHANGES-FROM-STEP7.patch").is_file():files.append(ROOT/"CHANGES-FROM-STEP7.patch")
    # B08 report and the externally bound B07 delivery verification are part of the release.
    files.extend(p for p in (ROOT/"development/b08").rglob("*") if p.is_file())
    files=sorted(set(files))
    if any(not p.is_file() for p in files):raise RuntimeError("missing release input")
    manifest=json.loads((ROOT/"outputs/validation-manifest.json").read_text(encoding="utf-8"))
    if (not manifest.get("acceptance_passed") or manifest["pytest_exit_code"] != 0
            or any(manifest["tests"][k] != 0 for k in ("failures","errors","skipped"))
            or not manifest.get("fixed_parity",{}).get("passed")
            or not manifest.get("v2_acceptance",{}).get("passed")):
        raise RuntimeError("release requires zero-skip passing tests, JDK 17 parity and V2 acceptance")
    if version == "0.3.0":
        final_path=ROOT/"outputs/final/acceptance.json"
        if not final_path.is_file():raise RuntimeError("0.3.0 requires clause-by-clause final acceptance")
        final=json.loads(final_path.read_text())
        if (not final.get("acceptance_passed") or final.get("unresolved_contracts") or
            final.get("validation_snapshot_sha256") != manifest.get("snapshot_sha256")):
            raise RuntimeError("0.3.0 acceptance is incomplete or does not match the current validated snapshot")
    elif (ROOT/"src/fogsim/simulation/cleanup.py").is_file():
        extended_path=ROOT/"outputs/step7/current-validation.json"
        if not extended_path.is_file() or not json.loads(extended_path.read_text()).get("planned_checks_passed"):
            raise RuntimeError("step7 release also requires V20/V21 and the current validation summary")
    for relative,expected in manifest["project_hashes"].items():
        actual=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
        if actual!=expected:raise RuntimeError(f"source changed after validation: {relative}")
    for prefix_path, relative_key in ((jroot, "files"),):
        integrity=json.loads((ROOT/"outputs/source-integrity-v2.json").read_text())
        for relative, expected in integrity[relative_key].items():
            if hashlib.sha256((prefix_path/relative).read_bytes()).hexdigest()!=expected:
                raise RuntimeError(f"original Java source/dependency changed: {relative}")
    output=args.output.resolve() if args.output else ROOT/f"{prefix}.zip"
    if output.suffix.lower() != ".zip":raise ValueError("release output must be a .zip file")
    output.parent.mkdir(parents=True,exist_ok=True)
    hashes={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files:z.write(p,prefix+"/"+str(p.relative_to(ROOT)).replace("\\","/"))
        z.writestr(prefix+"/RELEASE-FILES.json",json.dumps(hashes,indent=2))
    with zipfile.ZipFile(output) as z:
        if z.testzip() is not None:raise RuntimeError("archive integrity failure")
        for relative,expected in hashes.items():
            if hashlib.sha256(z.read(prefix+"/"+relative)).hexdigest()!=expected:
                raise RuntimeError(f"archive mismatch: {relative}")
    print(json.dumps({"archive":str(output),"files":len(files)+1,"bytes":output.stat().st_size,
                      "sha256":hashlib.sha256(output.read_bytes()).hexdigest()},indent=2))


if __name__=="__main__":main()
