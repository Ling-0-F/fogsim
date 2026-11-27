"""Opt-in, per-engine acceptance observations at the actual leaf read.

No reference handle, extra evaluation, cached feature or shared evaluation state.
Ordinary production runs do not enable leaf observation.
"""
from copy import deepcopy
from types import MethodType
from fogsim.rules.gp import GPRule
from fogsim.gp.program import Opcode
from fogsim.serialization.f64 import encode_f64

class GPObservations:
    def __init__(self,engine,*,dynamic=False):
        self.feature_observations=[];self.boundaries={};self.dynamic=dynamic
        if dynamic:
            self._snapshot=engine._snapshot
            original=self._snapshot
            def snapshot(current):
                data=original()
                if current.run_status=='RUNNING' and current.trace.enabled:
                    self.boundaries.setdefault(current.processed_event_count,[]).append({d.id:len(current.event_queue.staging_heaps[d]) for d in current.state.mobile_devices})
                return data
            engine._snapshot=MethodType(snapshot,engine)
        for role in ('routing','sequencing'):
            delegate=getattr(engine,role+'_rule');collector=self
            class Observed:
                def __init__(self,delegate,role):self.delegate,self.role=delegate,role
                def priority(self,option,context):
                    leaf=[]
                    def callback(instruction,value):
                        leaf.append(dict(node_index=instruction.node_index,kind='feature' if instruction.opcode==Opcode.READ_FEATURE else 'constant',
                            name=instruction.operand.value if instruction.opcode==Opcode.READ_FEATURE else 'constant',value=encode_f64(value)))
                    try:
                        return self.delegate.priority(option,context,observer=callback) if type(self.delegate) is GPRule else self.delegate.priority(option,context)
                    finally:
                        key=[option.task.workflow.id,option.task.java_index,option.resource.id] if collector.dynamic else list(option.key)
                        collector.feature_observations.append(dict(event_sequence=engine.processed_event_count,time=context.view.clock_time,role=self.role,option=key,reads=leaf))
            setattr(engine,role+'_rule',Observed(delegate,role))
        engine.gp_observations=self

def attach_observer(engine,*,dynamic=False):
    if hasattr(engine,'gp_observations'):raise ValueError('GP observer already installed')
    return GPObservations(engine,dynamic=dynamic)
