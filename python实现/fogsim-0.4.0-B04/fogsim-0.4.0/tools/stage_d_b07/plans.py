"""Physical business fixtures; no expected AST, score, selection, or future state."""
from copy import deepcopy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def gp(text):return dict(kind='gp',expression=text)
def times(pt,ut=0.,dt=0.):
    return dict(processing_time=float(pt),upload_time=float(ut),download_time=float(dt))
def resources(devices=1,*,local=True,cloud=True):
    return [dict(id=f'M{i}',type='MOBILE',can_process_tasks=local) for i in range(devices)]+[dict(id='E0',type='EDGE')]+([dict(id='C0',type='CLOUD')] if cloud else [])
def task(name,owner='M0',pt=2.):
    return dict(id=name,execution_times={owner:times(pt),'E0':times(pt),'C0':times(pt)})
def workflow(wid,owner,release,tasks,dependencies=()):
    return dict(id=wid,owner_device_id=owner,release_time=float(release),tasks=tasks,dependencies=list(dependencies))
def instance(rs,ws):return dict(time_unit='s',resources=rs,workflows=ws)
def scene(name,family,physical,routing,sequencing,**meta):
    return dict(id=name,family=family,instance=physical,routing_rule=routing,sequencing_rule=sequencing,**meta)

def diamond():
    main=[task('R',pt=3.),task('A',pt=2.),task('B',pt=4.),task('J',pt=2.)]
    for t in main[1:]:
        t['execution_times']['E0']['processing_time']+=2.
        t['execution_times']['C0']['processing_time']+=2.
    jobs=[workflow(0,'M0',0.,main,[['R','A'],['R','B'],['A','J'],['B','J']])]
    # Under FCFS the first two helpers occupy E0/C0 and the third queues at
    # M0; fixed_resource and GP also really queue helpers before R finishes.
    for wid,release in [(1,.25),(2,.5),(3,.75)]:
        jobs.append(workflow(wid,'M0',release,[task('Q',pt=10.)]))
    return instance(resources(),jobs)

def shared():
    jobs=[]
    for wid,pt in enumerate((10.,2.,4.)):
        owner='M0' if wid<2 else 'M1'
        jobs.append(workflow(wid,owner,float(wid),[dict(id='T',execution_times={owner:times(50.),'E0':times(pt,1.,1.)})]))
    return instance(resources(2,cloud=False),jobs)

def changing():
    jobs=[]
    for wid,clock in [(0,0.),(1,2.)]:
        owner=f'M{wid}'
        jobs.append(workflow(wid,owner,clock,[dict(id='T',execution_times={'E0':times(4.,1.,1.),'C0':times(4.,1.,1.)})]))
    return instance(resources(2,local=False),jobs)

def cache(resource,sign):
    queue=[.1,.2,.3] if sign=='positive' else [.5,.1]
    jobs=[]
    arrivals=[.1,.2,.3] if sign=='positive' else [.1,.1]
    for wid,(clock,pt) in enumerate([(0.,1.)]+list(zip(arrivals,queue))+[(3.,.4)]):
        options={'M0':times(20.),'E0':times(20.),'C0':times(20.)}
        options[resource]=times(pt, .1 if resource!='M0' and wid>0 else 0., .2 if resource!='M0' and wid>0 else 0.)
        jobs.append(workflow(wid,'M0',clock,[dict(id='T',execution_times=options)]))
    return instance(resources(),jobs)

def fixed_plan():
    out=[]
    chain=json.loads((ROOT/'data/cases/chain_remote.json').read_text())
    out.append(scene('F01-chain','F01',chain,gp('(+ MRT (+ PT (+ TWT (* 0 NTR))))'),gp('(- 0 (+ NTR PT))')))
    for route in ['fcfs','fixed_resource','gp']:
        for sequence in ['fcfs','gp']:
            r=gp('(+ PT (* 0 (+ MRT WIQ)))') if route=='gp' else dict(kind=route,**({'resource_id':'E0'} if route=='fixed_resource' else {}))
            s=gp('(- 0 PT)') if sequence=='gp' else dict(kind='fcfs')
            out.append(scene(f'F02-{route}-{sequence}','F02',diamond(),r,s))
    out.append(scene('F03-multidevice-queue','F03',shared(),gp('PT'),gp('(- 0 PT)')))
    out.append(scene('F04-state-routing','F04',changing(),gp('(+ PT (+ MRT WIQ))'),gp('(- 0 PT)')))
    for resource in ['M0','E0','C0']:
        for sign in ['positive','negative']:
            out.append(scene(f'F05-{resource}-{sign}','F05',cache(resource,sign),
                gp('(+ PT (* 0 (+ WIQ TTIQ)))'),gp('(+ WIQ TTIQ)'),target_resource=resource,residual_sign=sign))
    special={'NAN':'(* 1e309 0)','POSITIVE_INFINITY':'(* 1e308 1e308)',
        'NEGATIVE_INFINITY':'(* -1e308 1e308)','POSITIVE_ZERO':'(/ 1e-300 1e300)',
        'NEGATIVE_ZERO':'(/ -1e-300 1e300)'}
    for kind,text in special.items():
        out.append(scene('F06-'+kind,'F06',shared(),gp(text),gp(text),score_class=kind))
    return dict(format='fogsim.b07-fixed-plan',schema_version=1,cases=out)

DAX={
    'chain':'<adag><job id="R"/><job id="A"/><job id="J"/><child ref="A"><parent ref="R"/></child><child ref="J"><parent ref="A"/></child></adag>\n',
    'fork_join':'<adag><job id="R"/><job id="A"/><job id="B"/><job id="J"/><child ref="A"><parent ref="R"/></child><child ref="B"><parent ref="R"/></child><child ref="J"><parent ref="A"/><parent ref="B"/></child></adag>\n',
}

def dynamic_plan():
    return dict(format='fogsim.b07-dynamic-plan',schema_version=1,cases=[
        dict(id='D09A-chain',shape='chain',seed=31,N=2,W=1,devices=1,edges=1,clouds=1,local=True,
            routing_rule=gp('(+ PT (+ UT DT))'),sequencing_rule=gp('(- 0 PT)'),require_shared_nonfirst=False),
        dict(id='D09A-shared-fork-join',shape='fork_join',seed=31,N=2,W=2,devices=2,edges=1,clouds=0,local=True,
            routing_rule=gp('(+ PT (* 0 (+ MRT WIQ)))'),sequencing_rule=gp('(- 0 TIS)'),require_shared_nonfirst=True),
        dict(id='D09A-no-local',shape='chain',seed=7,N=1,W=1,devices=2,edges=1,clouds=1,local=False,
            routing_rule=gp('(+ MRT (+ TTIQ (+ PT (+ UT DT))))'),sequencing_rule=gp('(- 0 PT)'),require_shared_nonfirst=False),
    ])

def write_plans(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name,value in [('fixed-plan-v2.json',fixed_plan()),('dynamic-plan-v3.json',dynamic_plan())]:
        p=directory/name
        if p.exists():raise ValueError('plan already exists: '+str(p))
        p.write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n')
    for shape,xml in DAX.items():
        p=directory/shape/'CyberShake_30.xml';p.parent.mkdir()
        p.write_text(xml)
