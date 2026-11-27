"""Immutable candidate archive, fixed validation selection and portable rules."""
from pathlib import Path
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from fogsim.gp.identity import validate_rule_manifest
from .protocols import canonical, identity, Snapshot, write_json, read_json
from .fitness import compare


class CandidateArchive:
    def __init__(self):
        self._rows=[]
        self._frozen=False

    def add(self,individual,generation,evaluation_ref):
        if self._frozen:raise RuntimeError('candidate archive is frozen')
        row=individual.record()
        occurrence=dict(generation=generation,individual_id=individual.individual_id,
            birth_sequence=individual.birth_sequence,plan_id=individual.evaluation['plan_id'],evaluation_ref=evaluation_ref,
            training_fitness=individual.evaluation['fitness'])
        existing=next((r for r in self._rows if r['rule_pair_id']==row['rule_pair_id']),None)
        if existing is None:
            self._rows.append(dict(candidate_index=len(self._rows),rule_pair_id=row['rule_pair_id'],
                rules=row['rules'],rule_manifest=row['rule_manifest'],first_occurrence=occurrence,occurrences=[occurrence]))
        else:existing['occurrences'].append(occurrence)

    def freeze(self,output):
        self._frozen=True
        snap=Snapshot(canonical(dict(format='fogsim.candidate-archive',schema_version=1,candidates=self._rows)))
        doc=snap.to_dict();doc['archive_id']=identity('candidate-archive',doc)
        write_json(output,doc)
        return Snapshot(canonical(doc))


def prepared_candidate(candidate):
    rules=candidate['rules']
    object_fields(rules,('routing','sequencing'),where='candidate.rules')
    prepared=prepare_rules(RuleSpec.from_mapping('routing',rules['routing']),RuleSpec.from_mapping('sequencing',rules['sequencing']))
    validate_rule_manifest(candidate['rule_manifest'],prepared_rules=prepared)
    if candidate['rule_pair_id']!=prepared.rule_pair_id:raise InputError('candidate identity mismatch')
    return prepared


def choose_validation(candidates,evaluations):
    if len(candidates)!=len(evaluations):raise InputError('missing validation evaluation')
    winner=None
    for i,value in enumerate(evaluations):
        if value['status']=='INCOMPLETE':raise RuntimeError('incomplete validation')
        if value['status']=='FEASIBLE' and (winner is None or compare(value,evaluations[winner])<0):winner=i
    return winner


def freeze_selected(candidate,validation,archive,trial_id,trees,path):
    payload=dict(format='fogsim.selected-rule',schema_version=1,trial_id=trial_id,
        candidate_index=candidate['candidate_index'],candidate_archive_id=archive['archive_id'],
        selection_policy='fixed_validation_first_occurrence_v1',validation_plan_id=validation['plan_id'],
        validation_evaluation_id=validation['evaluation_id'],validation_fitness=validation['fitness'],
        rules=candidate['rules'],rule_manifest=candidate['rule_manifest'],rule_pair_id=candidate['rule_pair_id'],trees=trees)
    doc=payload|dict(selected_rule_id=identity('selected-rule',payload))
    prepared_candidate(doc)
    write_json(path,doc)
    return Snapshot(canonical(doc))


def load_selected_rule(path):
    doc=read_json(path)
    object_fields(doc,('format','schema_version','trial_id','candidate_index','candidate_archive_id','selection_policy',
        'validation_plan_id','validation_evaluation_id','validation_fitness','rules','rule_manifest','rule_pair_id','trees',
        'selected_rule_id'),where='selected-rule')
    if doc['format']!='fogsim.selected-rule' or type(doc['schema_version']) is not int or doc['schema_version']!=1:
        raise InputError('unsupported selected-rule protocol')
    from fogsim.input_validation import integer,finite,text
    integer(doc['candidate_index'],'candidate_index',0)
    finite(doc['validation_fitness'],'validation_fitness')
    text(doc['trial_id'],'trial_id')
    import re
    for key in ('candidate_archive_id','validation_plan_id','validation_evaluation_id','selected_rule_id','rule_pair_id'):
        if type(doc[key]) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}',doc[key]) is None:
            raise InputError(f'invalid {key}')
    if doc['selection_policy']!='fixed_validation_first_occurrence_v1':raise InputError('unsupported selection policy')
    if identity('selected-rule',{k:v for k,v in doc.items() if k!='selected_rule_id'})!=doc['selected_rule_id']:
        raise InputError('selected-rule identity mismatch')
    from .config import parse_training_config
    checked=parse_training_config(dict(format='fogsim.training-config',schema_version=1,mode='single_routing',
        plans=dict(training='x',validation='y',test='z'),trees=doc['trees']),Path.cwd()).to_dict()['trees']
    if checked!=doc['trees']:raise InputError('selected-rule limits must be resolved')
    return prepared_candidate(doc),Snapshot(canonical(doc))


def evaluate_selected_rule(rule_file,plan,output_dir,**kwargs):
    from .evaluation import evaluate_rule_pair
    prepared,selected=load_selected_rule(rule_file)
    return evaluate_rule_pair(prepared,plan,output_dir,trees=selected.to_dict()['trees'],**kwargs)
