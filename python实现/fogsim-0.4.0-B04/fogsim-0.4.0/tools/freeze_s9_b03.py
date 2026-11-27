"""Freeze B03 code/config/adapters/contracts without altering B01/B02 snapshots."""
from pathlib import Path
import argparse,json,hashlib
from fogsim.training.protocols import write_json,identity
from freeze_s9_b02 import files as inherited_files,ROOT

def files():
    result=inherited_files()
    for rel in ('README.md','docs/SOURCE-DISTRIBUTION.md','docs/TRAINING-PROTOCOL-B03.md','docs/RUNNING-S9-B03.md',
                'development/S9-B03/PLAN.md','development/S9-B03/dependency-lock.json'):
        result[rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
    return dict(sorted(result.items()))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','verify']);p.add_argument('--output',required=True);a=p.parse_args();path=Path(a.output);current=files()
    if a.action=='freeze':
        if path.exists():raise RuntimeError('refuse to overwrite frozen checkpoint')
        write_json(path,dict(format='fogsim.source-freeze',schema_version=1,batch='S9-B03',files=current,source_freeze_id=identity('source-freeze',current)))
        print(identity('source-freeze',current))
    else:
        expected=json.loads(path.read_text())['files'];changes=[k for k in sorted(expected.keys()|current.keys()) if expected.get(k)!=current.get(k)]
        print(json.dumps(dict(passed=not changes,files=len(current),differences=changes)))
        if changes:raise SystemExit(1)
if __name__=='__main__':main()
