"""B06 input-only vectors and physical queue-history fixtures; no expected outputs."""
from copy import deepcopy
from pathlib import Path
import json,math
ROOT=Path(__file__).resolve().parents[1]
BITS=('0000000000000000','8000000000000000','3ff0000000000000','bff0000000000000','4000000000000000','c000000000000000',
      '0000000000000001','8000000000000001','0010000000000000','8010000000000000','7fefffffffffffff','ffefffffffffffff',
      '7ff0000000000000','fff0000000000000','7ff8000000000011','7ff8000000000022')
def tag(bits):return dict(kind='f64',bits=bits)
def rule(expression):return dict(kind='gp',expression=expression)
def instance():
    resources=[dict(id='M0',type='MOBILE',can_process_tasks=True),dict(id='M1',type='MOBILE',can_process_tasks=True),dict(id='E0',type='EDGE'),dict(id='C0',type='CLOUD')]
    workflows=[]
    for wid,owner,release,count in [(0,'M0',5.,4),(1,'M1',9.,3)]:
        tasks=[]
        for i in range(count):
            pt=4. if i==0 else (.1 if i==1 else .2 if i==2 else 3.)
            if wid==1 and i==1:pt=.4
            times={owner:dict(processing_time=pt,upload_time=0.,download_time=0.),'E0':dict(processing_time=pt,upload_time=.5,download_time=.25),'C0':dict(processing_time=pt+1.,upload_time=1.5,download_time=.5)}
            tasks.append(dict(id='T'+str(i),execution_times=times))
        workflows.append(dict(id=wid,owner_device_id=owner,release_time=release,tasks=tasks,dependencies=[]))
    return dict(time_unit='s',resources=resources,workflows=workflows)
def fixture():return dict(instance=instance(),clock_time=20.,ready_times=[],available_times=[dict(resource_id=r,value=40.) for r in ['M0','M1','E0','C0']],queue_history=[],completed_options=[],pending_starts=[])
def state_case(name,f,role='routing',candidates=None,expression='(+ PT (+ WIQ (+ MRT (+ TWT NTR))))'):
    if candidates is None:candidates=[[0,'T0',r] for r in ['M0','E0','C0']]
    return dict(id=name,mode='state',fixture=f,role=role,candidates=candidates,routing_rule=rule(expression) if role=='routing' else dict(kind='fcfs'),sequencing_rule=rule(expression) if role=='sequencing' else dict(kind='fcfs'))
def cases():
    out=[]
    for op in ['+','-','*','/','Max','Min']:
        for a in BITS:
            for b in BITS:out.append(dict(id=f'function/{op}/{a}/{b}',mode='function',op=op,a=tag(a),b=tag(b)))
    valid=['PT','-1','.5','1.','1e+3','1d','1F','010','-010','-0.0','1e309','-1e309','1e-9999','-1e-9999',
        '2.2250738585072014e-308','2.225073858507201e-308','4.9406564584124654e-324','1.7976931348623157e308',
        '1.7976931348623159e308','9007199254740993','1.00000000000000011102230246251565404236316680908203125',
        '(+ PT (* UT DT))','( +\tPT\r\n1.0 )','(+ (+ 1e16 -1e16) 1)','(+ 1e16 (+ -1e16 1))',
        '(/ (* 1e309 0) -0.0)','(Max 0.0 -0.0)','(Min -0.0 0.0)','(+ (* PT PT) (+ UT PT))','(+(* PT UT)(/ DT 2))']
    valid+=['NIQ','WIQ','MRT','UT','DT','TTIQ','TIS','TWT','NTR']
    for i,text in enumerate(valid):
        out.append(dict(id=f'parse/valid/{i}',mode='parse',expression=text,role='routing',field_path='routing_rule.expression'))
        out.append(state_case(f'evaluation/valid/{i}',fixture(),candidates=[[0,'T0','E0']],expression=text))
    for i,row in enumerate(json.loads((ROOT/'tests/gp/b02/cases/parser-errors.json').read_text())):
        out.append(dict(id='parse/error/'+row['name'],mode='parse',expression=row['text'],role='sequencing',field_path='run.sequencing_rule.expression'))
    for direction in ['left','right']:
        text='1'
        for _ in range(2500):text='(+ '+text+' 1)' if direction=='left' else '(+ 1 '+text+')'
        out.append(dict(id='parse/depth2500/'+direction,mode='parse',expression=text,role='routing',field_path='expression'))
        out.append(state_case('evaluation/depth2500/'+direction,fixture(),expression=text))
    vectors=json.loads((ROOT/'development/b04/evidence/encoding-vectors/common-inputs.json').read_text())
    for c in vectors['cases']:out.append(dict(id='manifest/'+c['id'],mode='manifest',routing_rule=c['routing'],sequencing_rule=c['sequencing']))
    for i,v in enumerate(vectors['cj_values']):out.append(dict(id=f'cj/valid/{i}',mode='cj',payload=v))
    for i,v in enumerate([True,None,-1,1.5,{'x':'\ud800'},{'x':'\udfff'}]):out.append(dict(id=f'cj/invalid/{i}',mode='cj',payload=v))
    for bits in vectors['score_bits']:out.append(dict(id='f64/'+bits,mode='f64',value=tag(bits)))
    for i,v in enumerate([0,dict(kind='f64',bits='0'*15),dict(kind='f64',bits='ABCDEF0000000000'),dict(kind='f64',bits='0'*16,value=0),dict(kind='f32',bits='0'*16)]):out.append(dict(id=f'f64/invalid/{i}',mode='f64',value=v))
    for resource in ['M0','E0','C0']:
        for shape in ['empty','two','emptied_positive','emptied_negative','roundoff_nonempty']:
            f=fixture();keys=[[0,'T1',resource],[0,'T2',resource]]
            if shape!='empty':f['queue_history']=[dict(action='enqueue',option=k) for k in keys]
            if shape=='emptied_negative':
                f['instance']['workflows'][0]['tasks'][1]['execution_times'][resource]['processing_time']=.5
                f['instance']['workflows'][0]['tasks'][2]['execution_times'][resource]['processing_time']=.1
            if shape.startswith('emptied'):f['queue_history'] +=[dict(action='remove',option=k) for k in keys]
            if shape=='roundoff_nonempty':
                f['instance']['workflows'][0]['tasks'][1]['execution_times'][resource]['processing_time']=1e16
                f['instance']['workflows'][0]['tasks'][2]['execution_times'][resource]['processing_time']=1.
                f['queue_history'].append(dict(action='remove',option=keys[0]))
            f['completed_options']=[[0,'T3',resource]]
            out.append(state_case(f'features/{resource}/{shape}',f))
            if shape in ('two','roundoff_nonempty'):
                queue=keys if shape=='two' else keys[1:]
                out.append(state_case(f'sequencing/{resource}/{shape}',deepcopy(f),'sequencing',queue,'(- 0 (+ PT TWT))'))
    for phase in ['arrival','successor_before_visit','after_visit','finish_registered','reserved_before_start']:
        f=fixture()
        if phase=='arrival':f['clock_time']=5.;f['ready_times']=[dict(option=[0,'T0',r],value=5.) for r in ['M0','E0','C0']]
        if phase=='after_visit':f['ready_times']=[dict(option=[0,'T0','E0'],value=12.)]
        if phase=='finish_registered':f['completed_options']=[[0,'T3','E0']]
        if phase=='reserved_before_start':f['available_times']=[dict(resource_id='E0',value=14.)];f['pending_starts']=[dict(option=[0,'T1','E0'],start_time=20.)]
        out.append(state_case('timing/'+phase,f,expression='(+ MRT (+ TWT (+ NTR TIS)))'))
    for resource in ['E0','C0']:
        f=fixture();keys=[[0,'T1',resource],[1,'T1',resource]];f['queue_history']=[dict(action='enqueue',option=k) for k in keys]
        f['ready_times']=[dict(option=keys[0],value=12.),dict(option=keys[1],value=7.)];f['completed_options']=[[0,'T3','E0']]
        out.append(state_case('shared/'+resource,f,'sequencing',keys,'(- 0 PT)'))
    for expr in ['PT','(- 0 PT)','(* (- UT PT) 0)','(* (- UT PT) 1e309)','(* 1e309 0)','1e309','-1e309','0.0','-0.0']:
        f=fixture();t=f['instance']['workflows'][0]['tasks'][0]['execution_times'];t['E0'].update(processing_time=1.,upload_time=2.);t['C0'].update(processing_time=2.,upload_time=.5)
        out.append(state_case('selection/routing/'+expr,f,candidates=[[0,'T0',r] for r in ['E0','C0','M0']],expression=expr))
        out.append(state_case('selection/single/'+expr,deepcopy(f),candidates=[[0,'T0','E0']],expression=expr))
    f=fixture();t=f['instance']['workflows'][0]['tasks'][0]['execution_times'];t['E0']['processing_time']=math.nextafter(1.,math.inf);t['C0']['processing_time']=1.
    out.append(state_case('selection/one-ulp',f,candidates=[[0,'T0','E0'],[0,'T0','C0']],expression='PT'))
    for expr in ['PT','(- 0 PT)','(* (- UT PT) 0)','(* (- UT PT) 1e309)','(* 1e309 0)','1e309','-1e309','0.0','-0.0']:
        f=fixture();keys=[[1,'T1','E0'],[0,'T1','E0']]
        f['instance']['workflows'][0]['tasks'][1]['execution_times']['E0'].update(upload_time=.01)
        f['instance']['workflows'][1]['tasks'][1]['execution_times']['E0'].update(upload_time=.8)
        f['queue_history']=[dict(action='enqueue',option=k) for k in keys]
        out.append(state_case('selection/sequencing/'+expr,f,'sequencing',keys,expr))
    f=fixture();keys=[[0,'T1','E0'],[1,'T1','E0']]
    f['instance']['workflows'][0]['tasks'][1]['execution_times']['E0']['processing_time']=math.nextafter(1.,math.inf)
    f['instance']['workflows'][1]['tasks'][1]['execution_times']['E0']['processing_time']=1.
    f['queue_history']=[dict(action='enqueue',option=k) for k in keys]
    out.append(state_case('selection/sequencing/one-ulp',f,'sequencing',keys,'PT'))
    for tie in ['release','owner','workflow','stable']:
        f=fixture();ws=f['instance']['workflows'];ws[0]['release_time']=8. if tie=='release' else 5.;ws[1]['release_time']=5.
        if tie=='workflow':
            ws[0]['id']=10;ws[1]['id']=3;ws[1]['owner_device_id']='M0'
            for t in ws[1]['tasks']:t['execution_times']['M0']=t['execution_times'].pop('M1')
            keys=[[10,'T1','E0'],[3,'T1','E0']]
        elif tie=='stable':keys=[[0,'T2','E0'],[0,'T1','E0']]
        else:keys=[[1,'T1','E0'],[0,'T1','E0']]
        f['queue_history']=[dict(action='enqueue',option=k) for k in keys]
        out.append(state_case('selection/tie/'+tie,f,'sequencing',keys,'0.0'))
    return dict(format='fogsim.gp-probe-input',schema_version=1,cases=out)

def legacy_differences():
    expressions=['(/ 1 -0.0)','(/ -1 -0.0)','(/ 0 -0.0)','(/ -0.0 -0.0)','(/ 1e309 -0.0)','(/ -1e309 -0.0)',
        '(/ (* 1e309 0) -0.0)','(/ 2 (* -1 0))','(/ 1 (/ -1e-300 1e300))','(+ 2 (/ 1 -0.0))','(Max 0 (/ 1 -0.0))','(Min 2 (/ -1 -0.0))']
    out=[]
    for i,e in enumerate(expressions):out.append(state_case(f'legacy/negative-zero/{i}',fixture(),candidates=[[0,'T0','E0']],expression=e))
    f=fixture();f['instance']['resources'][0]['can_process_tasks']=False
    for w in f['instance']['workflows']:
        if w['owner_device_id']=='M0':
            for t in w['tasks']:t['execution_times'].pop('M0')
    t=f['instance']['workflows'][0]['tasks'][0]['execution_times'];t['E0'].update(processing_time=1.,upload_time=2.);t['C0'].update(processing_time=1.,upload_time=.5)
    out.append(state_case('legacy/changed-selection',f,candidates=[[0,'T0','E0'],[0,'T0','C0']],expression='(/ 1 (* (- UT PT) (- WIQ WIQ)))'))
    return dict(format='fogsim.gp-probe-input',schema_version=1,cases=out)
