"""Build the cumulative B02 source-indexed package without rewriting B01."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST='S9-B02-FILES.json'
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def verify(root):
    doc=json.loads((root/MANIFEST).read_text());errors=[]
    for rel,row in doc['files'].items():
        p=root/rel
        if not p.is_file() or p.is_symlink() or p.stat().st_size!=row['bytes'] or sha(p.read_bytes())!=row['sha256']:errors.append(rel)
    return dict(passed=not errors,files=len(doc['files']),mismatches=errors)
def build(root,output):
    if output.exists() or root in output.parents:raise ValueError('output must be new and outside project root')
    accepted=json.loads((root/'outputs/step9/B02/acceptance.json').read_text())
    if not accepted['acceptance_passed']:raise ValueError('B02 gates have not passed')
    index=json.loads((root/'SOURCE-INDEX.json').read_text());indexed={e['path']:e for e in index['entries']}
    paths=[];excluded=[]
    for p in sorted(root.rglob('*')):
        if p.is_dir():continue
        rel=p.relative_to(root).as_posix();parts=p.relative_to(root).parts
        if any(s in ('.b02-deps','__pycache__','.pytest_cache','.git') for s in parts):continue
        if p.is_symlink():continue
        if rel in indexed:
            if sha(p.read_bytes())!=indexed[rel]['sha256']:raise ValueError('restored source modified: '+rel)
            continue
        if p.suffix in ('.pyc','.class'):
            excluded.append(dict(path=rel,bytes=p.stat().st_size,sha256=sha(p.read_bytes()),reason='rebuildable generated artifact'));continue
        if rel not in (MANIFEST,'B02-EXCLUDED-GENERATED.json'):paths.append(p)
    write(root/'B02-EXCLUDED-GENERATED.json',dict(format='fogsim.excluded-generated',schema_version=1,files=excluded))
    paths.append(root/'B02-EXCLUDED-GENERATED.json')
    files={p.relative_to(root).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in paths}
    write(root/MANIFEST,dict(format='fogsim.batch-files',schema_version=1,batch='S9-B02',files=files,
        source_index_sha256=sha((root/'SOURCE-INDEX.json').read_bytes())))
    paths.append(root/MANIFEST);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('fogsim-0.4.0/','')
        for p in paths:z.write(p,'fogsim-0.4.0/'+p.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as z:
        if z.testzip():raise ValueError('CRC failure')
    return dict(file=output.name,bytes=output.stat().st_size,sha256=sha(output.read_bytes()),top_directory='fogsim-0.4.0/',files=len(paths),excluded_indexed=len(indexed),excluded_generated=len(excluded))
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['build','verify']);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--output',type=Path);a=p.parse_args()
    result=verify(a.root.resolve()) if a.action=='verify' else build(a.root.resolve(),a.output.resolve())
    print(json.dumps(result,indent=2));return 0 if result.get('passed',True) else 1
if __name__=='__main__':raise SystemExit(main())
