from pathlib import Path
import signal,faulthandler,time,json,traceback,sys
from fogsim.training.config import load_training_config
from fogsim.training.plans import build_training_plans
from fogsim.training.runtime import run_entry
from fogsim.training.deap_adapter import prepare_dual,from_expression
from fogsim.training.protocols import write_json

def timeout(signum,frame):raise TimeoutError('controlled B03 diagnostic deadline')
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path('outputs/step9/B03/diagnostic');root.mkdir(parents=True,exist_ok=True)
faulthandler.dump_traceback_later(3)
signal.signal(signal.SIGALRM,timeout);signal.alarm(5)
start=time.monotonic()
try:
 cfg=load_training_config('configs/training/smoke-dual.json');entry=build_training_plans(cfg).training[0].to_dict()['entries'][0]
 prepared=prepare_dual(tuple(map(from_expression,['(* PT TIS)','(- (/ TWT TTIQ) (- NTR PT))'])))
 result,archive=run_entry(entry,prepared,'train',lambda p:write_json(root/'partial.json',p))
 write_json(root/'result.json',result);write_json(root/'input.json',archive)
except BaseException as exc:
 write_json(root/'exception.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc(),elapsed_seconds=time.monotonic()-start,capture_complete=False))
 raise
finally:signal.alarm(0);faulthandler.cancel_dump_traceback_later()
