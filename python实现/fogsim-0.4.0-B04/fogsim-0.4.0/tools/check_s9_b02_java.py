"""Independent ECJ local execution; common inputs contain no expected outputs."""
import argparse,json,os,subprocess,time,shutil
from pathlib import Path
from copy import deepcopy
from java_stage_d_support import compile_stage_d,environment
from java_support import ROOT,ORIGINAL,sha
from fogsim.training.protocols import write_json,read_json
from fogsim.training.deap_adapter import from_expression,to_expression,Individual
from fogsim.training.operators import generate,tournament,select_node,crossover,replace,check_tree
from fogsim.training.config import TREES

class Draws:
    def __init__(self,ints=(),reals=()):self.ints=list(ints);self.reals=list(reals)
    def randrange(self,start,stop=None):
        if stop is None:start,stop=0,start
        x=self.ints.pop(0)
        if not start<=x<stop:raise ValueError((start,stop,x))
        return x
    def random(self):return self.reals.pop(0)

def chain(h,text='PT'):
    for _ in range(h):text=f'(+ {text} UT)'
    return text

def full(h):return 'PT' if h==0 else f'(+ {full(h-1)} {full(h-1)})'

def cases():
    rows=[]
    def add(kind,**kw):rows.append(dict(case_id=f'{kind}-{sum(c["kind"]==kind for c in rows):02d}',kind=kind,**kw))
    for e in range(7):add('generate',height=1,method='grow',ints=[e,2,4] if e<6 else [6,9],reals=[.1])
    for f in range(10):add('generate',height=0,method='grow',ints=[f],reals=[.1])
    for h in (1,2,3):
        def draws(d):return [5] if d==h else [0]+draws(d+1)+draws(d+1)
        add('generate',height=h,method='full',ints=draws(0),reals=[.9])
    add('tournament',fitnesses=[1,1,2],size=7,ints=[1,1,0,2,1,0,1])
    add('tournament',fitnesses=[2,1,3],size=3,ints=[0,2,1])
    for expr,ints,reals in [('(+ (- PT PT) PT)',[0],[.1]),('(+ (- PT PT) PT)',[1],[.1]),('(+ (- PT PT) PT)',[2],[.99]),('PT',[],[.1]),('PT',[0],[.99])]:
        # Java bypasses nextInt when the single tree has no functions.
        add('node',a=expr,ints=ints,reals=reals)
    for a,b,pa,pb,n,tries in [
        ('(+ PT UT)','(- DT MRT)',[0],[0],2,1),
        (chain(7),'(+ PT UT)',[7],[0],2,1),
        ('(+ PT UT)',chain(7),[0],[7],2,1),
        ('(+ PT UT)',chain(7),[0],[7],1,1),
        (chain(7),'(+ PT UT)',[7,0],[0,0],2,2),
        (chain(7),'(+ PT UT)',[7,7],[0,0],2,2)]:
        add('cross',a=a,b=b,positions_a=pa,positions_b=pb,outputs=n,attempts=tries)
    # Both directions fail: one exceeds height, the other the independent node budget.
    add('cross',a=chain(4,full(3)),b=f'(+ (+ {chain(4)} UT) {full(3)})',positions_a=[4],positions_b=[2],outputs=2,attempts=1,max_nodes=31)
    for a,pos,sub in [('(+ PT UT)',0,'DT'),(chain(7),7,'(+ DT MRT)'),(chain(7),6,'(+ DT MRT)')]:add('mutation',a=a,position=pos,subtree=sub)
    add('elite');add('last_generation')
    for d in (.1,.85,.99):
        for n in (1,2):add('multi',capacity=n,reals=[d])
    return rows

def python_case(c,out):
    kind=c['kind'];rng=Draws(c.get('ints',[]),c.get('reals',[]))
    if kind=='generate':
        tree=generate(c['height'],c['method'],rng)
        return dict(expression=to_expression(tree),height=tree.height,nodes=len(tree))
    if kind=='tournament':
        pop=[]
        for i,f in enumerate(c['fitnesses']):
            ind=Individual(from_expression('PT'),str(i),i,{})
            ind.set_evaluation(dict(plan_id='same',status='FEASIBLE',fitness=f));pop.append(ind)
        winner,meta=tournament(pop,c['size'],rng);return dict(winner=int(winner.individual_id))
    if kind=='node':
        # Original ECJ avoids the int call when there are no functions.
        if c['a']=='PT' and not rng.ints:rng.ints=[0]
        return dict(index=select_node(from_expression(c['a']),rng=rng)[0])
    if kind=='cross':
        # Translate common preorder positions to category-local controlled draws.
        a,b=from_expression(c['a']),from_expression(c['b']);ints=[];reals=[]
        for i,j in zip(c['positions_a'],c['positions_b']):
            for tree,pos in ((a,i),(b,j)):
                fn=tree[pos].arity==2;eligible=[k for k,n in enumerate(tree) if (n.arity==2)==fn]
                ints.append(eligible.index(pos));reals.append(.1 if fn else .99)
        children,meta=crossover(a,b,dict(TREES,max_nodes=c.get('max_nodes',255)),c['attempts'],c['outputs'],Draws(ints,reals))
        return dict(children=list(map(to_expression,children)),parents=[to_expression(a),to_expression(b)],outputs=len(children))
    if kind=='mutation':
        from fogsim.training import operators
        a=from_expression(c['a']);pos=c['position'];fn=a[pos].arity==2
        eligible=[i for i,n in enumerate(a) if (n.arity==2)==fn]
        original=operators.generate
        try:
            operators.generate=lambda target,method,rng:from_expression(c['subtree'])
            children,_=operators.mutate(a,TREES,rng=Draws([eligible.index(pos)],[.1 if fn else .99]))
        finally:operators.generate=original
        return dict(children=list(map(to_expression,children)),parents=[to_expression(a)])
    if kind=='elite':
        from fogsim.training.config import load_training_config
        from fogsim.training.evolution import next_generation
        import random
        cfg=load_training_config(ROOT/'configs/training/smoke-single.json').to_dict()
        cfg['evolution'].update(population_size=3,elite_count=1,operator_weights=dict(crossover=0,mutation=0,reproduction=1))
        pop=[]
        for i,(expr,f) in enumerate([('PT',2),('UT',1),('DT',3)]):
            ind=Individual(from_expression(expr),str(i),i,{});ind.set_evaluation(dict(plan_id='same',status='FEASIBLE',fitness=f));pop.append(ind)
        state=random.getstate()
        try:random.seed(50);children,_,_,_=next_generation(pop,cfg,'java-component',1,3)
        finally:random.setstate(state)
        elite=children[-1]
        return dict(expression=to_expression(elite.tree),position=2,evaluated=elite.evaluation is not None,independent=all(elite.tree is not i.tree for i in pop))
    if kind=='last_generation':
        from fogsim.training.config import load_training_config,parse_training_config
        from fogsim.training.plans import build_training_plans
        from fogsim.training.evolution import run_trial
        from fogsim.training.protocols import read_jsonl
        import random
        class Pipe:
            def send(self,message):pass
            def recv(self):return 'START'
        raw=load_training_config(ROOT/'configs/training/smoke-single.json').to_dict();raw.pop('resolution_root')
        raw['evolution'].update(population_size=1,elite_count=0,operator_weights=dict(crossover=0,mutation=0,reproduction=1))
        cfg=parse_training_config(raw,ROOT);plans=build_training_plans(cfg)
        pmap=dict(training=[p.to_dict() for p in plans.training],validation=plans.validation.to_dict(),test=plans.test.to_dict())
        state=random.getstate()
        try:result=run_trial(Pipe(),cfg.to_dict(),pmap,out/'last-generation-python','java-component',123)
        finally:random.setstate(state)
        gens=read_jsonl(out/'last-generation-python/generations.jsonl')['rows']
        return dict(evaluated_last_population=gens[-1]['generation']==3 and gens[-1]['population_size']==1,
            evaluated_generations=result['generations_evaluated'],no_breeding_or_rotation=gens[-1]['reproduction'] is None)
    if kind=='multi':
        from fogsim.training.operators import choose_operator
        name,_=choose_operator(dict(crossover=.8,mutation=.15,reproduction=.05),rng)
        return dict(outputs=min(c['capacity'],2 if name=='crossover' else 1))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--java',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
    out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    write_json(out/'inputs.json',dict(cases=cases()))
    build=compile_stage_d(out/'build',a.java)
    source=ROOT/'tools/java/s9/fogsim/adapter/S9Operators.java';snapshot=out/'source/fogsim/adapter/S9Operators.java';snapshot.parent.mkdir(parents=True);shutil.copyfile(source,snapshot)
    classes=out/'classes';classes.mkdir();classpath=build['manifest']['builds']['target']['runtime_classpath']
    argv=[str(Path(a.java).with_name('javac')),'-encoding','UTF-8','-cp',classpath,'-sourcepath',str(ORIGINAL/'src'),'-d',str(classes),str(snapshot)]
    p=subprocess.run(argv,capture_output=True,text=True,env=environment(a.java));write_json(out/'compile.json',dict(argv=argv,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr,source_sha256=sha(source)))
    if p.returncode:raise RuntimeError(p.stderr)
    argv=[a.java,'-cp',os.pathsep.join((str(classes),classpath)),'fogsim.adapter.S9Operators',str(out/'inputs.json'),str(out/'java.json')]
    p=subprocess.run(argv,capture_output=True,text=True,env=environment(a.java));write_json(out/'process.json',dict(argv=argv,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
    if p.returncode:raise RuntimeError(p.stderr)
    python=[dict(case_id=c['case_id'],result=python_case(c,out)) for c in cases()];write_json(out/'python.json',dict(cases=python))
    java=read_json(out/'java.json')['cases'];checks=[]
    for j,p in zip(java,python):
        actual={k:v for k,v in j['result'].items() if k!='random_calls'}
        checks.append(dict(case_id=p['case_id'],passed=j['case_id']==p['case_id'] and actual==p['result'],java=actual,python=p['result']))
    summary=dict(passed=all(c['passed'] for c in checks),checks=checks,executed=len(checks),
        scope='J01/J02/J03 single-tree crossover+mutation and J06 exclusive call cardinality; elite/re-evaluation/generation lifecycle verified in Python; J04 dual-tree deferred')
    write_json(out/'checks.json',summary)
    if not summary['passed']:raise RuntimeError('Java/Python local difference')
    print(json.dumps(dict(passed=True,checks=len(checks))))
if __name__=='__main__':main()
