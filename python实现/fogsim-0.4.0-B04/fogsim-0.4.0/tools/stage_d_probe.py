"""Independent Python half of B06 common-input probes. No Java output is read."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import argparse,json
from fogsim.gp.ast import BinaryNode,ConstantNode
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression,CompiledExpression,Opcode
from fogsim.gp.evaluator import evaluate
from fogsim.gp.identity import canonical_json,expression_record
from fogsim.gp.features import Feature,read_feature
from fogsim.gp.diagnostics import GPInputError
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec,NUMERIC_SEMANTICS_VERSION
from fogsim.rules.contexts import StateView,RoutingContext,SequencingContext
from fogsim.rules.selection import choose_route,choose_next
from fogsim.serialization.f64 import encode_f64,decode_f64
from fogsim.instances.fixed import parse_instance
from fogsim.simulation.state import build_state
from fogsim.model.execution import Execution

def load_fixture(f):
    state=build_state(parse_instance(f['instance']));state.clock_time=float(f['clock_time'])
    state.active_workflows.update(state.workflows_by_id);state.pending_arrivals.clear()
    options={o.key:o for t in state.tasks_by_key.values() for o in t.options}
    for r in f['ready_times']:options[tuple(r['option'])].ready_time=float(r['value'])
    for r in f['available_times']:state.resources_by_id[r['resource_id']].available_time=float(r['value'])
    for h in f['queue_history']:
        o=options[tuple(h['option'])];o.task.dispatched=True
        if h['action']=='enqueue':o.resource.enqueue(o)
        elif h['action']=='remove':o.resource.remove_waiting(o)
        else:raise ValueError('invalid queue history action')
    for k in f['completed_options']:
        o=options[tuple(k)];o.task.dispatched=o.task.completed=True
        o.task.workflow.completed_executions.append(Execution(o,0.))
    for h in f['pending_starts']:
        o=options[tuple(h['option'])];o.task.dispatched=True;o.resource.pending_start=Execution(o,float(h['start_time']))
    return state,options

def snapshot(state):
    return dict(clock_time=state.clock_time,resources=[dict(id=r.id,numeric_id=r.numeric_id,type=r.resource_type.value,available_time=r.available_time,
        queued_processing_time=r.waiting_processing_time,queued_total_time=r.waiting_total_time,waiting_queue=[list(o.key) for o in r.waiting_queue],
        pending_start=list(r.pending_start.option.key) if r.pending_start else None) for r in state.resources_by_id.values()],
        workflows=[dict(id=w.id,owner_device_id=w.owner_device.id,release_time=w.release_time,completed_records=[e.task.id for e in w.completed_executions],
            tasks=[dict(id=t.id,dispatched=t.dispatched,completed=t.completed,options=[dict(resource_id=o.resource.id,processing_time=o.processing_time,
                upload_time=o.upload_time,download_time=o.download_time,ready_time=o.ready_time,priority=encode_f64(o.priority)) for o in t.options]) for t in w.tasks]) for w in state.workflows_by_id.values()])

def observation(instruction,value):
    return dict(node_index=instruction.node_index,kind='feature' if instruction.opcode==Opcode.READ_FEATURE else 'constant',
        name=instruction.operand.value if instruction.opcode==Opcode.READ_FEATURE else 'constant',value=encode_f64(value))

def run_case(c):
    mode=c['mode'];base=dict(id=c['id'],status='OK')
    if mode=='cj':
        try:return base|dict(canonical=canonical_json(c['payload']).decode('ascii'))
        except (ValueError,TypeError):return dict(id=c['id'],status='REJECTED')
    if mode=='f64':
        try:return base|dict(value=encode_f64(decode_f64(c['value'])))
        except GPInputError:return dict(id=c['id'],status='REJECTED')
    if mode=='parse':
        try:return base|dict(expression=expression_record(compile_expression(parse_expression(c['expression'],role=c['role'],field_path=c['field_path']))))
        except GPInputError as e:return dict(id=c['id'],status='PARSE_ERROR',diagnostic=e.diagnostic.to_dict())
    if mode=='manifest':return base|dict(rule_manifest=prepare_rules(RuleSpec.from_mapping('routing',c['routing_rule']),RuleSpec.from_mapping('sequencing',c['sequencing_rule'])).rule_manifest)
    if mode=='function':
        root=BinaryNode(c['op'],ConstantNode(c['a']['bits']),ConstantNode(c['b']['bits']));p=CompiledExpression(root);reads=[]
        value=evaluate(p,None,None,observer=lambda i,v:reads.append(observation(i,v)))
        return base|dict(value=encode_f64(value),reads=reads)
    if mode!='state':raise ValueError('unknown probe mode')
    state,options=load_fixture(c['fixture']);prepared=prepare_rules(RuleSpec.from_mapping('routing',c['routing_rule']),RuleSpec.from_mapping('sequencing',c['sequencing_rule']))
    candidates=tuple(options[tuple(k)] for k in c['candidates']);view=StateView.from_state(state)
    context=RoutingContext(candidates[0].task,candidates,view) if c['role']=='routing' else SequencingContext(candidates[0].resource,candidates,view)
    before=snapshot(state);features=[dict(option=list(o.key),values={f.value:encode_f64(read_feature(f,o,context)) for f in Feature}) for o in candidates]
    pure=snapshot(state);scores=[];reads=[];delegate=getattr(prepared,c['role'])
    class Observed:
        def priority(self,o,ctx):
            leaf=[]
            def wrapped(compiled,option,context):return evaluate(compiled,option,context,observer=lambda i,v:leaf.append(observation(i,v)))
            try:
                with patch('fogsim.rules.gp.evaluate',wrapped):v=delegate.priority(o,ctx)
            finally:reads.append(dict(option=list(o.key),reads=leaf))
            scores.append(dict(option=list(o.key),priority=encode_f64(v)));return v
    chosen=(choose_route if c['role']=='routing' else choose_next)(context,Observed())
    return base|dict(rule_manifest=prepared.rule_manifest,loaded=before,after_features=pure,features=features,reads=reads,scores=scores,
        selected=list(chosen.key),selected_is_candidate=any(o is chosen for o in candidates),after_selection=snapshot(state),rng_is_null=True)

def run_document(value):
    if value['format']!='fogsim.gp-probe-input' or type(value['schema_version']) is not int or value['schema_version']!=1:raise ValueError('invalid probe input')
    return dict(format='fogsim.gp-probe-output',schema_version=1,numeric_semantics_version=NUMERIC_SEMANTICS_VERSION,cases=[run_case(c) for c in value['cases']])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(run_document(json.loads(a.input.read_text())),ensure_ascii=True,indent=2,allow_nan=False)+'\n')
