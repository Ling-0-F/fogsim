"""Execute original ECJ dual operators and independent Python controlled cases."""
import argparse,os,json,subprocess,shutil
from pathlib import Path
from copy import deepcopy
from java_stage_d_support import compile_stage_d,environment
from java_support import ROOT,ORIGINAL,sha
from fogsim.training.protocols import read_json,write_json
from fogsim.training.config import TREES
from fogsim.training.deap_adapter import from_expression,to_expression
from fogsim.training.dual_operators import crossover_dual,mutate_dual
from fogsim.training import operators
from check_s9_b02_java import Draws,chain,full


def cases():
    rows=[]
    def add(kind,**data):rows.append(dict(case_id=f'{kind}-{len(rows):03d}',kind=kind,**data))
    for slot in (0,1):
        pairs=[('(+ PT UT)','(- DT MRT)',[0],[0],255),
            ('(+ PT UT)',chain(7,'DT'),[0],[7],255),
            (chain(7),'(+ DT MRT)',[7],[0],255),
            (chain(4,full(3)),f'(+ (+ {chain(4)} UT) {full(3)})',[4],[2],31),
            ('(+ PT (* UT DT))','(- MRT NIQ)',[1],[0],255),
            (chain(7),chain(7,'DT'),[7,0],[0,7],255),
            (chain(7),'(+ DT MRT)',[7,0],[0,0],255),
            (chain(7),'(+ DT MRT)',[7,7],[0,0],255)]
        for left,right,pa,pb,nodes in pairs:
            a=['NIQ','PT'];b=['TIS','DT'];a[slot]=left;b[slot]=right
            add('cross',a=a,b=b,slot=slot,positions_a=pa,positions_b=pb,attempts=len(pa),outputs=2,max_nodes=nodes)
        for left,right,pa,pb,attempts in [('(+ PT UT)',chain(7,'DT'),[0,0],[7,0],2),(chain(7),'(+ DT MRT)',[7,7],[0,0],2)]:
            a=['NIQ','PT'];b=['TIS','DT'];a[slot]=left;b[slot]=right
            add('cross',a=a,b=b,slot=slot,positions_a=pa,positions_b=pb,attempts=attempts,outputs=1)
        # Java's rejected cross-role slot draws are observed, not reproduced in Python.
        add('cross',a=['(+ PT UT)','(- DT MRT)'],b=['(Max TIS NTR)','(Min NIQ WIQ)'],slot=slot,
            positions_a=[0],positions_b=[0],attempts=1,outputs=2,unfixed=True,ints=[1-slot,slot,slot,slot])
        for height in (0,1,2,3):
            a=['NIQ','PT'];a[slot]='PT'
            add('mutation',a=a,slot=slot,positions=[0],subtrees=[chain(height,'DT')],attempts=1,ints=[slot])
        for positions,subtrees in [([7],['(+ DT MRT)']),([7,7],['(+ DT MRT)','DT']),([7,7],['(+ DT MRT)','(+ UT NIQ)'])]:
            a=['NIQ','PT'];a[slot]=chain(7)
            add('mutation',a=a,slot=slot,positions=positions,subtrees=subtrees,attempts=len(positions),ints=[slot])
    # Actual HalfBuilder + TerminalERCUniform twice, with independent role trees.
    add('initialize',trees=[dict(method='grow',height=1),dict(method='full',height=1)],ints=[6,9,0,5,3],reals=[.1,.9])
    add('initialize',trees=[dict(method='full',height=1),dict(method='grow',height=1)],ints=[2,0,1,6,8],reals=[.9,.1])
    return rows


def node_draws(tree,positions):
    ints=[];reals=[]
    for pos in positions:
        fn=tree[pos].arity==2;eligible=[i for i,n in enumerate(tree) if (n.arity==2)==fn]
        ints.append(eligible.index(pos));reals.append(.1 if fn else .99)
    return ints,reals


def child_record(trees):return dict(expressions=[to_expression(t) for t in trees],heights=[t.height for t in trees],nodes=[len(t) for t in trees])


def python_case(c):
    if c['kind']=='initialize':
        rng=Draws(c['ints'],[]);trees=[]
        for role,spec in zip(('sequencing','routing'),c['trees']):
            tree=operators.generate(spec['height'],spec['method'],rng)
            trees.append(dict(role=role,expression=to_expression(tree),height=tree.height,nodes=len(tree)))
        return dict(trees=trees)
    a=tuple(map(from_expression,c['a']));before=[to_expression(t) for t in a];slot=c['slot']
    if c['kind']=='cross':
        b=tuple(map(from_expression,c['b']));beforeB=[to_expression(t) for t in b];ints=[slot];reals=[]
        for pa,pb in zip(c['positions_a'],c['positions_b']):
            for tree,pos in ((a[slot],pa),(b[slot],pb)):
                i,r=node_draws(tree,[pos]);ints.extend(i);reals.extend(r)
        children,meta=crossover_dual(a,b,dict(TREES,max_nodes=c.get('max_nodes',255)),c['attempts'],c['outputs'],Draws(ints,reals))
        all_genomes=(a,b,*children)
        result=dict(children=[child_record(t) for t in children],legal_history=[r['legal'] for r in meta['attempts']],attempts=len(meta['attempts']),parents_unchanged=before==[to_expression(t) for t in a] and beforeB==[to_expression(t) for t in b])
    else:
        ints,reals=node_draws(a[slot],c['positions']);ints.insert(0,slot);subtrees=iter(c['subtrees']);original=operators.generate
        try:
            operators.generate=lambda height,method,rng:from_expression(next(subtrees))
            children,meta=mutate_dual(a,TREES,c['attempts'],Draws(ints,reals))
        finally:operators.generate=original
        all_genomes=(a,*children)
        result=dict(children=[child_record(t) for t in children],legal_history=[r['legal'] for r in meta['attempts']],attempts=len(meta['attempts']),parents_unchanged=before==[to_expression(t) for t in a])
    groups=[{id(n) for t in genome for n in t} for genome in all_genomes]
    result['disjoint']=all(not x&y for i,x in enumerate(groups) for y in groups[i+1:]) and all(not {id(n) for n in g[0]}&{id(n) for n in g[1]} for g in all_genomes)
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--java',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    common=cases();write_json(out/'inputs.json',dict(cases=common))
    build=compile_stage_d(out/'build',a.java)
    sources=[]
    for name in ('S9Operators.java','S9DualOperators.java'):
        p=ROOT/'tools/java/s9/fogsim/adapter'/name;dest=out/'source/fogsim/adapter'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);sources.append(dest)
    classes=out/'classes';classes.mkdir();cp=build['manifest']['builds']['target']['runtime_classpath']
    argv=[str(Path(a.java).with_name('javac')),'-encoding','UTF-8','-cp',cp,'-sourcepath',str(ORIGINAL/'src'),'-d',str(classes),*map(str,sources)]
    r=subprocess.run(argv,capture_output=True,text=True,env=environment(a.java));write_json(out/'compile.json',dict(argv=argv,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr,adapter_sources={p.name:sha(p) for p in sources},original_dual_crossover_sha256=sha(ORIGINAL/'src/mengxu/algorithm/multipletreegp/AllIndexAllSwapCrossoverPipeline.java')))
    if r.returncode:raise RuntimeError(r.stderr)
    argv=[a.java,'-cp',os.pathsep.join((str(classes),cp)),'fogsim.adapter.S9DualOperators',str(out/'inputs.json'),str(out/'java.json')]
    r=subprocess.run(argv,capture_output=True,text=True,env=environment(a.java));write_json(out/'process.json',dict(argv=argv,exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr))
    if r.returncode:raise RuntimeError(r.stderr)
    python=[dict(case_id=c['case_id'],result=python_case(c)) for c in common];write_json(out/'python.json',dict(cases=python))
    java=read_json(out/'java.json')['cases'];checks=[]
    for j,p in zip(java,python):
        actual={k:v for k,v in j['result'].items() if k!='random_calls'}
        checks.append(dict(case_id=p['case_id'],passed=j['case_id']==p['case_id'] and actual==p['result'],java=actual,python=p['result']))
    summary=dict(passed=len(java)==len(python)==len(common) and all(c['passed'] for c in checks),executed=len(checks),checks=checks,scope='J04 dual original pipeline four combinations/both roles, tails/retries/parent preservation/clone isolation; both mutation roles; actual two-tree HalfBuilder initialization')
    write_json(out/'checks.json',summary)
    if not summary['passed']:raise RuntimeError('Java/Python local difference')
    print(json.dumps(dict(passed=True,checks=len(checks))))
if __name__=='__main__':main()
