"""Exact comparison of all trial artifacts, except declared duration observations."""
import argparse,json,hashlib
from pathlib import Path
from fogsim.training.protocols import read_json,read_jsonl,write_json,canonical,identity

def semantic_files(root):
    files={}
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(root).as_posix()
        if path.suffix=='.json':value=read_json(path)
        elif path.suffix=='.jsonl':
            parsed=read_jsonl(path)
            if parsed['interrupted_tail']:raise RuntimeError('uncommitted JSONL tail: '+relative)
            value=parsed['rows']
            if path.name=='generations.jsonl':value=[{k:v for k,v in row.items() if k!='duration_seconds'} for row in value]
        else:value={'bytes_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        files[relative]=identity('semantic-file',value)
    return files

def compare_roots(left,right):
    rows=[]
    for trial in sorted(p.name for p in left.glob('trial-*') if p.is_dir()):
        a,b=semantic_files(left/trial),semantic_files(right/trial)
        differences=[k for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)]
        rows.append(dict(trial_id=trial,files_left=len(a),files_right=len(b),differences=differences,
            semantic_id=identity('trial-semantics',a),passed=not differences))
    return dict(format='fogsim.training-reproducibility',schema_version=1,passed=bool(rows) and all(r['passed'] for r in rows),
        exclusions=[dict(file='trial-*/generations.jsonl',field='duration_seconds',reason='monotonic elapsed observation')],trials=rows)

def main():
    p=argparse.ArgumentParser();p.add_argument('left');p.add_argument('right');p.add_argument('--output',required=True);a=p.parse_args()
    result=compare_roots(Path(a.left),Path(a.right));write_json(a.output,result);print(json.dumps(result));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
