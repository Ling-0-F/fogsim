from pathlib import Path
from importlib.metadata import version
import json,jsonschema
from fogsim.training.protocols import write_json,source_provenance
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'outputs/step9/B03'
formats={'fogsim.evolution-result':'evolution-result','fogsim.training-result':'training-result','fogsim.selected-rule':'selected-rule','fogsim.candidate-archive':'candidate-archive'}
checked=[]
for folder in ('dual-first','dual-repeat','cases-final'):
 for p in sorted((out/folder).rglob('*.json')):
  if p.name not in ('evolution-result.json','training-result.json','selected_rule.json','archive.json'):continue
  d=json.loads(p.read_text());kind=formats.get(d.get('format'))
  if kind:
   jsonschema.validate(d,json.loads((ROOT/('schemas/training/'+kind+'.schema.json')).read_text()));checked.append(p.relative_to(ROOT).as_posix())
write_json(out/'schema-final.json',dict(passed=True,checked=len(checked),files=checked,jsonschema_version=version('jsonschema'),source=source_provenance()))
print('validated schemas',len(checked))
