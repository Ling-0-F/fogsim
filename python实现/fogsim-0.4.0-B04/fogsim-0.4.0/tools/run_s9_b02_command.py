"""Record exact argv/environment, raw stdout/stderr, exit and elapsed time."""
import argparse,os,subprocess,sys,time,platform,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--record',required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    command=a.command[1:] if a.command[:1]==['--'] else a.command
    out=Path(a.record);out.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with out.with_suffix('.stdout.txt').open('wb') as stdout,out.with_suffix('.stderr.txt').open('wb') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr)
    row=dict(argv=command,cwd=str(Path.cwd()),exit_code=result.returncode,duration_seconds=time.monotonic()-started,
        python=sys.version,platform=platform.platform(),environment={k:os.environ[k] for k in ('PYTHONPATH','PYTEST_DISABLE_PLUGIN_AUTOLOAD','FOGSIM_JAVA','LD_LIBRARY_PATH') if k in os.environ},
        stdout=out.with_suffix('.stdout.txt').name,stderr=out.with_suffix('.stderr.txt').name)
    out.write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(dict(record=str(out),exit_code=result.returncode,duration_seconds=row['duration_seconds'])));return result.returncode
if __name__=='__main__':raise SystemExit(main())
