"""Build disjoint complete local packages; verify any part without old workspaces."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from restore_sources import safe_relative
ROOT=Path(__file__).resolve().parents[1]
MANIFEST="S9-B04-FILES.json"
PARTS=("main","evidence","references","rollback")
SUMMARY={"acceptance.json","source-freeze.json","source-audit.json","contracts-audit.json",
    "schema-audit.json","independent-selected-check.json","no-deap.json","wheel-check.json",
    "unit-final.xml","regression.xml","recorded-simulation-counts.json"}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
    return h.hexdigest()


def write(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n")


def classify(rel,indexed):
    parts=Path(rel).parts
    if rel.startswith("rollback/S9-"):return "rollback"
    if rel in indexed or rel.startswith("references/java/") or rel.startswith("rollback/"):return "references"
    if any(s in ("wheels","test-wheels","dist") for s in parts):return "references"
    if rel.startswith("outputs/step9/B04/") and len(parts)==4 and Path(rel).name in SUMMARY:return "main"
    if rel.startswith("outputs/") or (rel.startswith("development/") and any(s in ("evidence","cases","java-build") for s in parts)):return "evidence"
    return "main"


def verify(root,part="all"):
    doc=json.loads((root/MANIFEST).read_text());errors=[];checked=0
    for rel,row in doc["files"].items():
        safe_relative(rel)
        if part!="all" and row["part"]!=part:continue
        p=root/rel;checked+=1
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=row["bytes"] or sha(p)!=row["sha256"]:errors.append(rel)
    return dict(passed=not errors,part=part,files=checked,mismatches=errors)


def build(root,output):
    if output.exists() and any(output.iterdir()):raise ValueError("output must be absent or empty")
    if root==output or root in output.parents:raise ValueError("output must be outside project")
    if not json.loads((root/"outputs/step9/B04/acceptance.json").read_text())["acceptance_passed"]:raise ValueError("final acceptance has not passed")
    indexed={e["path"]:e for e in json.loads((root/"SOURCE-INDEX.json").read_text())["entries"]}
    for rel,row in indexed.items():
        p=root/rel
        if not p.is_file() or sha(p)!=row["sha256"]:raise ValueError("restored source missing/changed: "+rel)
    files={};excluded=[]
    for p in sorted(root.rglob("*")):
        if p.is_dir():continue
        rel=p.relative_to(root).as_posix();parts=p.relative_to(root).parts
        if rel in (MANIFEST,"B04-EXCLUDED-GENERATED.json"):continue
        if p.is_symlink():
            excluded.append(dict(path=rel,reason="generated symbolic link"));continue
        if any(s in ("__pycache__",".pytest_cache",".git",".venv","build",".b02-deps",".b03-deps",".b04-deps") or s.endswith(".egg-info") for s in parts) and rel not in indexed:
            # Keep evidence build environment/manifests; only compiled/cache material is disposable.
            if "build" not in parts or p.suffix in (".class",".pyc") or any(s in ("__pycache__",".pytest_cache",".git",".venv") or s.endswith(".egg-info") for s in parts):
                excluded.append(dict(path=rel,bytes=p.stat().st_size,sha256=sha(p),reason="rebuildable cache/install artifact"));continue
        if p.suffix in (".pyc",".class") and rel not in indexed:
            excluded.append(dict(path=rel,bytes=p.stat().st_size,sha256=sha(p),reason="rebuildable generated artifact"));continue
        files[rel]=dict(bytes=p.stat().st_size,sha256=sha(p),part=classify(rel,indexed))
    write(root/"B04-EXCLUDED-GENERATED.json",dict(format="fogsim.excluded-generated",schema_version=1,files=excluded))
    p=root/"B04-EXCLUDED-GENERATED.json";files[p.name]=dict(bytes=p.stat().st_size,sha256=sha(p),part="main")
    write(root/MANIFEST,dict(format="fogsim.batch-files",schema_version=1,batch="S9-B04",files=files,
        source_index_sha256=sha(root/"SOURCE-INDEX.json"),complete_local=True))
    output.mkdir(parents=True,exist_ok=True);packages=[]
    for part in PARTS:
        name="fogsim-0.4.0-B04"+("" if part=="main" else "-"+part)+".zip";target=output/name
        members=[rel for rel,row in files.items() if row["part"]==part]
        if part=="main":members.append(MANIFEST)
        with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
            archive.writestr("fogsim-0.4.0/","")
            for rel in sorted(members):archive.write(root/rel,"fogsim-0.4.0/"+rel)
        packages.append(dict(file=name,part=part,bytes=target.stat().st_size,sha256=sha(target),files=len(members),
            purpose={"main":"cumulative code, cases, contracts, manual and final summary","evidence":"original current/historical results, inputs, failures, Java outputs","references":"restored pinned sources and offline dependency wheels","rollback":"unchanged prior S9 deliveries"}[part],
            required_for_basic_use=part=="main",required_for_offline_training=part in ("main","references"),required_for_complete_review=True))
    index=dict(format="fogsim.delivery-parts",schema_version=1,batch="S9-B04",packages=packages,
        extraction_order=[p["file"] for p in packages],target="same new parent directory; all archives contain fogsim-0.4.0/",
        disjoint_file_paths=True,external_environment="JDK17 required for Java checks, not bundled; CPython3.12/Linux x86_64 offline wheels")
    write(output/"fogsim-0.4.0-B04-parts.json",index)
    return index


def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["build","verify"]);p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--output",type=Path);p.add_argument("--part",choices=["all",*PARTS],default="all");a=p.parse_args()
    result=verify(a.root.resolve(),a.part) if a.action=="verify" else build(a.root.resolve(),a.output.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get("passed",True) else 1
if __name__=="__main__":raise SystemExit(main())
