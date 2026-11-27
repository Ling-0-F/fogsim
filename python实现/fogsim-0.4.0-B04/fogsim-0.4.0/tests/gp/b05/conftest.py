import sys,json,os
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'unit'))
@pytest.fixture
def evidence(request):
    def write(name,value):
        if base:=os.environ.get('FOGSIM_B05_EVIDENCE'):
            path=Path(base)/request.node.name.replace('/','_');path.mkdir(parents=True,exist_ok=True)
            (path/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return write
