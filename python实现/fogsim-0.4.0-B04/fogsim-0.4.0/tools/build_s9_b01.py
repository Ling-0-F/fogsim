"""Package a fully accepted cumulative B01 snapshot; no historical gate rewriting."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    from fogsim.training.protocols import source_provenance
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    report=json.loads((ROOT/'outputs/step9/B01/acceptance.json').read_text())
    if not report['acceptance_passed'] or report['source']!=source_provenance():
        raise RuntimeError('B01 acceptance missing or source changed since validation')
    from accept_s9_b01 import audit
    if not audit()['passed']:raise RuntimeError('historical byte retention failed')
    manifest_path=ROOT/'S9-B01-FILES.json'
    paths=[p for p in sorted(ROOT.rglob('*')) if p.is_file() and not p.is_symlink()
           and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix!='.pyc' and p!=manifest_path
           and p.relative_to(ROOT).parts[0]!='build' and not any(x.endswith('.egg-info') for x in p.parts)]
    files={p.relative_to(ROOT).as_posix():dict(size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths}
    manifest_path.write_text(json.dumps(dict(format='fogsim.s9-B01-files',schema_version=1,files=files),indent=2)+'\n')
    paths.append(manifest_path)
    output=Path(args.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise RuntimeError('refusing to replace an existing package')
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        z.writestr('fogsim-0.4.0/','')
        for p in sorted(paths):
            rel='fogsim-0.4.0/'+p.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(rel,date_time=(2026,11,14,12,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(p.stat().st_mode & 0xffff)<<16
            z.writestr(info,p.read_bytes(),compresslevel=6)
    with zipfile.ZipFile(output) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failed')
    print(json.dumps(dict(package=str(output),bytes=output.stat().st_size,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),members=len(paths)+1)))

if __name__=='__main__':main()
