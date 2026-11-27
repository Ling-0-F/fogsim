"""One complete serial trial; runs only inside the supervised spawn worker."""
import random
import sys
import platform
import time
import traceback
from pathlib import Path
from .deap_adapter import make_individual, DUAL_ROLES
from .operators import initialize, tournament, crossover, mutate, reproduce, choose_operator, stable_feasible
from .dual_operators import initialize_dual, crossover_dual, mutate_dual, reproduce_dual
from .selection import CandidateArchive, prepared_candidate, choose_validation, freeze_selected, load_selected_rule
from .protocols import write_json, canonical, identity, source_provenance, append_jsonl, POLICY
from .runtime import preflight, run_entry
from .fitness import classify, summarize

IMPLEMENTATION='fogsim-training-single-B02-v1'
IMPLEMENTATIONS={'single_routing':IMPLEMENTATION,'dual_tree':'fogsim-training-dual-B03-v1'}


class TrialInterrupted(RuntimeError):pass


class TrialEvaluator:
    def __init__(self,conn,root,trial_id,trees,implementation=IMPLEMENTATION):
        self.conn,self.root,self.trial_id,self.trees=conn,Path(root),trial_id,trees
        self.sequence=0
        self.source=source_provenance()
        self.actual_runs=0
        self.attempted_runs=0
        self.implementation=implementation

    def emit(self,kind,**data):self.conn.send(dict(kind=kind,trial_id=self.trial_id,**data))

    def __call__(self,prepared,plan,relative):
        p=plan.to_dict();preflight(prepared,p,self.trees)
        output=self.root/relative
        if output.exists():raise RuntimeError('evaluation output already exists')
        output.mkdir(parents=True)
        binding=dict(rule_pair_id=prepared.rule_pair_id,plan_id=plan.plan_id,implementation_source_id=self.source['source_id'],
            implementation=self.implementation,failure_policy=POLICY,trial_id=self.trial_id,evaluation_sequence=self.sequence,trees=self.trees)
        self.sequence+=1
        records=[];interruption=None;complete=False;before=repr(random.getstate())
        def snapshot():
            return dict(format='fogsim.individual-evaluation',schema_version=1,evaluation_id=identity('evaluation',binding),
                **binding,rule_manifest=prepared.rule_manifest,**summarize(records,len(p['entries']),complete),runs=records,
                interruption=interruption,evolution_rng_unchanged=repr(random.getstate())==before)
        write_json(output/'plan.json',p)
        write_json(output/'provenance.json',dict(python=sys.version,platform=platform.platform(),start_method='spawn',**self.source))
        write_json(output/'evaluation.json',snapshot())
        self.emit('evaluation_started',evaluation_ref=relative+'/evaluation.json')
        for index,entry in enumerate(p['entries']):
            partial={}
            self.emit('run_started',index=index,run_id=entry['run_id'],evaluation_ref=relative+'/evaluation.json',
                seconds=p['limits']['wallclock_seconds_per_run'])
            if self.conn.recv()!='START':raise RuntimeError('invalid controller acknowledgement')
            self.attempted_runs+=1
            try:
                raw,archive=run_entry(entry,prepared,p['dataset_role'],partial.update,
                    on_config=lambda cfg:write_json(output/f'runs/{index:04d}/active_config.json',cfg))
                partial.update(result=raw,input=archive)
                classification=classify(raw)
                result_ref=f'runs/{index:04d}/result.json';input_ref=f'runs/{index:04d}/input.json' if archive is not None else None
                write_json(output/result_ref,raw)
                if input_ref:write_json(output/input_ref,archive)
                records.append(dict(index=index,run_id=entry['run_id'],classification=classification,status=raw['status'],
                    makespan=raw['makespan'],reason_code=raw.get('reason_code'),reason=raw.get('reason'),
                    result_ref=result_ref,input_ref=input_ref,raw_result=None,input_archive=None))
                self.actual_runs+=1
                write_json(output/'evaluation.json',snapshot())
            except BaseException as exc:
                interruption=dict(classification=getattr(exc,'classification','INPUT_OR_PLAN_ERROR' if isinstance(exc,ValueError) else 'PROGRAM_EXCEPTION'),
                    run_index=index,error_type=type(exc).__name__,message=str(exc))
                write_json(output/'failures/exception.json',dict(**interruption,traceback=traceback.format_exc(),partial=partial))
                write_json(output/'evaluation.json',snapshot())
                raise
            self.emit('run_completed',index=index,evaluation_ref=relative+'/evaluation.json',classification=classification)
        complete=True
        value=snapshot()
        if not value['evolution_rng_unchanged']:raise RuntimeError('simulation consumed evolution RNG')
        write_json(output/'evaluation.json',value)
        self.emit('evaluation_completed',evaluation_ref=relative+'/evaluation.json',status=value['status'])
        return value


def next_generation(population,cfg,trial_id,generation,birth_start):
    e,t=cfg['evolution'],cfg['trees']
    dual=cfg['mode']=='dual_tree'
    cross,mutation,copy_genome=(crossover_dual,mutate_dual,reproduce_dual) if dual else (crossover,mutate,reproduce)
    elites=stable_feasible(population)[:e['elite_count']]
    capacity=e['population_size']-len(elites)
    children=[];operations=[];birth=birth_start
    def newborn(tree,lineage):
        nonlocal birth
        individual=make_individual(tree,f'{trial_id}/g{generation:04d}/i{birth:06d}',birth,lineage,cfg['mode'])
        birth+=1
        children.append(individual)
    while len(children)<capacity:
        name,draw=choose_operator(e['operator_weights'])
        a,ta=tournament(population,e['tournament_size'])
        parents=[a];tournaments=[ta]
        if name=='crossover':
            b,tb=tournament(population,e['tournament_size']);parents.append(b);tournaments.append(tb)
            trees,operation=cross(a.genome,b.genome,t,e['crossover_attempts'],min(2,capacity-len(children)))
        elif name=='mutation':trees,operation=mutation(a.genome,t,e['mutation_attempts'])
        else:trees,operation=copy_genome(a.genome)
        opid=f'{trial_id}/g{generation:04d}/op{len(operations):04d}'
        operation.update(operation_id=opid,parents=[p.individual_id for p in parents],tournaments=tournaments,operator_draw=draw)
        # Record stable source IDs as well as local direction numbers.
        def bind_sources(source):
            for key in ('recipient','donor','fallback_parent','parent'):
                if type(source.get(key)) is int:source[key+'_id']=parents[source[key]].individual_id
            for child in source.get('trees',{}).values():bind_sources(child)
        for source in operation['sources']:bind_sources(source)
        for direction,tree in enumerate(trees):
            newborn(tree,dict(operator=name,operation_id=opid,direction=direction+1,parents=operation['parents'],source=operation['sources'][direction]))
        operation['children']=[p.individual_id for p in children[-len(trees):]]
        operations.append(operation)
    for parent in elites:
        source=dict(role='rule_pair' if dual else 'routing',parent_id=parent.individual_id)
        if dual:source['trees']={r:dict(kind='unchanged_clone',parent_id=parent.individual_id) for r in DUAL_ROLES}
        newborn(parent.genome,dict(operator='elite',parents=[parent.individual_id],source=source))
    if len(children)!=e['population_size'] or any(p.evaluation is not None or p.fitness.valid for p in children):
        raise RuntimeError('invalid next-generation size or stale fitness')
    summary=dict(operator_selections={n:sum(o['operator']==n for o in operations) for n in ('crossover','mutation','reproduction')},
        accepted_children=sum(o['accepted_children'] for o in operations),fallback_children=sum(o['fallback_children'] for o in operations),
        elite_count=len(elites),elite_sources=[p.individual_id for p in elites],next_population_size=len(children),scores_cleared=True)
    return children,operations,summary,birth


def run_trial(conn,cfg,plans,root,trial_id,seed):
    from .plans import parse_training_plan
    root=Path(root);root.mkdir()
    random.seed(seed)
    implementation=IMPLEMENTATIONS[cfg['mode']]
    evaluator=TrialEvaluator(conn,root,trial_id,cfg['trees'],implementation)
    result=dict(format='fogsim.evolution-result',schema_version=1,implementation=implementation,trial_id=trial_id,
        evolution_seed=seed,mode=cfg['mode'],training_status='INCOMPLETE',validation_status='NOT_STARTED',test_status='NOT_STARTED',
        candidate_archive_ref=None,selected_rule_ref=None,generations_evaluated=0,completed_simulations=0,attempted_simulations=0)
    archive=CandidateArchive()
    try:
        birth=0;population=[]
        for _ in range(cfg['evolution']['population_size']):
            tree,history=(initialize_dual if cfg['mode']=='dual_tree' else initialize)(cfg['trees'])
            population.append(make_individual(tree,f'{trial_id}/g0000/i{birth:06d}',birth,history,cfg['mode']));birth+=1
        for g,p in enumerate(plans['training']):
            generation_start=time.monotonic()
            plan=parse_training_plan(p)
            for ind in population:
                ind.validate(cfg['trees'])
                append_jsonl(root/'individuals.jsonl',ind.record())
                ref=f'evaluations/{ind.birth_sequence:06d}'
                ind.set_evaluation(evaluator(ind.prepare(),plan,ref))
                append_jsonl(root/'evaluated-individuals.jsonl',dict(individual_id=ind.individual_id,generation=g,
                    plan_id=plan.plan_id,evaluation_ref=ref+'/evaluation.json',status=ind.evaluation['status'],fitness=ind.evaluation['fitness']))
            feasible=stable_feasible(population)
            row=dict(generation=g,plan_id=plan.plan_id,population_size=len(population),feasible_count=len(feasible),
                fitnesses=[i.evaluation['fitness'] for i in population],duration_seconds=time.monotonic()-generation_start,individual_ids=[i.individual_id for i in population],
                evolution_rng_id=identity('evolution-rng',repr(random.getstate())),reproduction=None)
            result['generations_evaluated']=g+1
            if not feasible:
                append_jsonl(root/'generations.jsonl',row)
                result['training_status']='NO_FEASIBLE_INDIVIDUAL';break
            winner=feasible[0]
            archive.add(winner,g,f'evaluations/{winner.birth_sequence:06d}/evaluation.json')
            row['generation_winner']=winner.individual_id
            if g==cfg['evolution']['generations']-1:
                append_jsonl(root/'generations.jsonl',row)
                result['training_status']='COMPLETED';break
            population,operations,summary,birth=next_generation(population,cfg,trial_id,g+1,birth)
            for op in operations:append_jsonl(root/'operations.jsonl',op)
            row['reproduction']=summary
            append_jsonl(root/'generations.jsonl',row)
        frozen=archive.freeze(root/'candidates/archive.json').to_dict()
        result['candidate_archive_ref']='candidates/archive.json'
        if result['training_status']=='COMPLETED':
            evaluator.emit('candidates_frozen',archive_id=frozen['archive_id'],candidate_count=len(frozen['candidates']))
            validation_plan=parse_training_plan(plans['validation'])
            validations=[evaluator(prepared_candidate(c),validation_plan,f'validation/{i:04d}') for i,c in enumerate(frozen['candidates'])]
            selected=choose_validation(frozen['candidates'],validations)
            if selected is None:result['validation_status']='NO_VALIDATION_WINNER'
            else:
                result['validation_status']='SELECTED'
                frozen_selected=freeze_selected(frozen['candidates'][selected],validations[selected],frozen,trial_id,cfg['trees'],root/'selected_rule.json').to_dict()
                result['selected_rule_ref']='selected_rule.json'
                evaluator.emit('selected_rule_frozen',selected_rule_id=frozen_selected['selected_rule_id'])
                # Reload the written artifact through the independent, DEAP-free reader.
                prepared,_=load_selected_rule(root/'selected_rule.json')
                test=evaluator(prepared,parse_training_plan(plans['test']),'test')
                result['test_status']='COMPLETED' if test['status']=='FEASIBLE' else 'TEST_FAILED'
        result['status']='COMPLETED' if result['test_status']=='COMPLETED' else 'DOMAIN_FAILED'
    except BaseException as exc:
        result['status']='INCOMPLETE'
        result['interruption']=dict(error_type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
        write_json(root/'failures/exception.json',result['interruption'])
        raise
    finally:
        result['completed_simulations']=evaluator.actual_runs
        result['attempted_simulations']=evaluator.attempted_runs
        result['evolution_rng_id']=identity('evolution-rng',repr(random.getstate()))
        write_json(root/'evolution-result.json',result)
    return result


def trial_worker(conn,*args):
    try:conn.send(dict(kind='trial_done',result=run_trial(conn,*args)))
    except BaseException as exc:
        conn.send(dict(kind='error',error_type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()))
    finally:conn.close()
