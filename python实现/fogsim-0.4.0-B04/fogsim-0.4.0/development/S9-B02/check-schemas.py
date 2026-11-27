"""Validate actual B02 normal/domain/exception/interruption artifacts."""
from pathlib import Path
import json
from importlib.metadata import version
import jsonschema
from fogsim.training.protocols import write_json,source_provenance
ROOT=Path(__file__).resolve().parents[2]
root=ROOT/'outputs/step9/B02'
formats={'fogsim.evolution-result':'evolution-result','fogsim.training-result':'training-result','fogsim.selected-rule':'selected-rule','fogsim.candidate-archive':'candidate-archive'}
checked=[]
for folder in ['single-first','single-repeat','cases-final']:
 for p in sorted((root/folder).rglob('*.json')):
  if p.name not in ('evolution-result.json','training-result.json','selected_rule.json','archive.json'):continue
  doc=json.loads(p.read_text());key=formats.get(doc.get('format'))
  if key:
   jsonschema.validate(doc,json.loads((ROOT/('schemas/training/'+key+'.schema.json')).read_text()))
   checked.append(p.relative_to(ROOT).as_posix())
write_json(root/'schema-final.json',dict(passed=True,checked=len(checked),files=checked,jsonschema_version=version('jsonschema'),source=source_provenance(),scope='actual completed/domain/program/supervision outputs; INCOMPLETE contains only committed facts'))
print('schemas passed',len(checked))
