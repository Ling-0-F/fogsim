"""Content binding for implementation, tests, configs, adapters, protocols and lock."""
from pathlib import Path
import argparse,hashlib,json
from fogsim.training.protocols import write_json,identity
ROOT=Path(__file__).resolve().parents[1]

def files():
    paths=[]
    for name in ('src','tests','tools','configs','schemas'):
        paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.class'))
    paths.extend(ROOT/p for p in ('pyproject.toml','docs/TRAINING-PROTOCOL-B02.md','docs/RUNNING-S9-B02.md',
        'development/S9-B02/dependency-lock.json','development/S9-B02/requirements-train.lock'))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['freeze','verify']);ap.add_argument('--output',required=True);a=ap.parse_args();path=Path(a.output)
    current=files()
    if a.action=='freeze':
        if path.exists():raise RuntimeError('refuse to overwrite a frozen source checkpoint')
        value=dict(format='fogsim.source-freeze',schema_version=1,files=current,source_freeze_id=identity('source-freeze',current))
        write_json(path,value);print(value['source_freeze_id'])
    else:
        frozen=json.loads(path.read_text())['files'];differences=[p for p in sorted(frozen.keys()|current.keys()) if frozen.get(p)!=current.get(p)]
        print(json.dumps(dict(passed=not differences,files=len(current),differences=differences)))
        if differences:raise SystemExit(1)
if __name__=='__main__':main()
