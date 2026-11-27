from dataclasses import replace
from itertools import repeat
from fogsim import load_experiment_config
from fogsim.experiment_config import (WorkflowTypeRange, EnvironmentConfig, DynamicRunConfig,
    RealRange, RuleConfig)
from fogsim.randomness.samplers import ExponentialSampler

SINGLE = '<adag><job id="T"/></adag>'
CHAIN = '<adag><job id="Z"/><job id="a"/><child ref="a"><parent ref="Z"/></child></adag>'
DIAMOND = '<adag><job id="root"/><job id="left"/><job id="right"/><job id="join"/>' + \
    '<child ref="join"><parent ref="right"/><parent ref="left"/></child>' + \
    '<child ref="right"><parent ref="root"/></child><child ref="left"><parent ref="root"/></child></adag>'


def config(tmp_path, *, xml=SINGLE, seed=7, devices=1, edges=0, clouds=0, local=True,
           N=1, W=1, max_events=1000, trace=True, invariants=True, target=None):
    from conftest import ROOT
    dax = tmp_path/'dax'; dax.mkdir(exist_ok=True)
    (dax/'CyberShake_30.xml').write_text(xml)
    cfg = load_experiment_config(ROOT/'configs/examples/step1_dynamic.json')
    params = replace(cfg.source.samplers, workload=RealRange(1,2),data_size=RealRange(0,1),edge_data=RealRange(0,1),
        processing_rate_device=RealRange(10,20),processing_rate_edge=RealRange(20,30),processing_rate_cloud=RealRange(30,40))
    return replace(cfg, source=replace(cfg.source,seed=seed,dag_root=dax,workflow_types=WorkflowTypeRange(0,0),
        environment=EnvironmentConfig(devices,edges,clouds,local),samplers=params),
        run=DynamicRunConfig(N,W,max_events=max_events,trace_enabled=trace,check_invariants=invariants,
                             routing_rule=RuleConfig('fixed_resource',target) if target else RuleConfig()))


def intervals(monkeypatch, values):
    iterator = iter(values)
    original = ExponentialSampler.sample
    calls = []
    def sample(self,rng):
        original(self,rng)  # retain a real draw, then control only the business interval
        value = float(next(iterator)); calls.append((rng,value)); return value
    monkeypatch.setattr(ExponentialSampler,'sample',sample)
    return calls
