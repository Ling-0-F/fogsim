"""B06 independent source snapshots; complete explicit JDK17, never a compiler fallback."""
from pathlib import Path
import difflib,hashlib,json,os,shutil,subprocess,time
from java_support import ROOT,ORIGINAL,java_tools,reference_jdk,sha

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=True,indent=2,allow_nan=False)+'\n')
def environment(java):
    jdk=Path(java).resolve().parent.parent
    return dict(os.environ,LD_LIBRARY_PATH=os.pathsep.join((str(jdk/'lib'),str(jdk/'lib/server'),os.environ.get('LD_LIBRARY_PATH',''))))
def build_fingerprint(manifest):
    payload={k:manifest[k] for k in ('original_sources','dependencies','adapter_sources')}
    payload['overlays']={k:v['patches'] for k,v in manifest['builds'].items()}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def compile_stage_d(output,explicit):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    java,javac=java_tools(explicit,allow_compiler_module=False);env=environment(java)
    # reference_jdk uses subprocess; its process inherits the selected JDK library path.
    version_proc=subprocess.run([str(java),'-XshowSettings:properties','-version'],env=env,capture_output=True,text=True)
    compiler=subprocess.run([str(javac),'-version'],env=env,capture_output=True,text=True)
    write(out/'environment.json',dict(java_path=str(java),java_sha256=sha(java),javac_path=str(javac),javac_sha256=sha(javac),
        modules_sha256=sha(java.parent.parent/'lib/modules'),java_argv=version_proc.args,java_exit_code=version_proc.returncode,
        java_stdout=version_proc.stdout,java_stderr=version_proc.stderr,javac_argv=compiler.args,javac_exit_code=compiler.returncode,
        javac_stdout=compiler.stdout,javac_stderr=compiler.stderr,environment={'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']},jdk21_executed=False))
    if version_proc.returncode or 'java.specification.version = 17' not in version_proc.stderr or compiler.returncode or not (compiler.stdout+compiler.stderr).startswith('javac 17.'):
        raise RuntimeError('INFRASTRUCTURE_ERROR: actual java and javac must be complete JDK17')
    original_files=sorted((ORIGINAL/'src').rglob('*.java'));jars=sorted(p for p in (ORIGINAL/'libraries').glob('*.jar') if 'javadoc' not in p.name)
    baseline={p.relative_to(ORIGINAL/'src').as_posix():sha(p) for p in original_files}
    adapters=sorted((ROOT/'tools/java/stage_d').rglob('*.java'))
    shared=[ROOT/'tools/java/src/fogsim/adapter/Json.java',ROOT/'tools/java/src/fogsim/adapter/FixedInstanceMain.java']
    manifest=dict(original_sources=baseline,dependencies={p.relative_to(ROOT).as_posix():sha(p) for p in jars},
        adapter_sources={p.relative_to(ROOT).as_posix():sha(p) for p in [*adapters,*shared]},builds={},jdk='environment.json')
    adapter_snapshot=out/'adapter-source'
    for p in [*adapters,*shared]:
        rel=Path('fogsim/adapter')/p.name;dest=adapter_snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    snapshot_mains=sorted(adapter_snapshot.rglob('*.java'))
    classpath=os.pathsep.join(map(str,jars))
    for flavor in ('target','original'):
        folder=out/flavor;source=folder/'source';source.mkdir(parents=True);patches=[]
        for p in original_files:
            rel=p.relative_to(ORIGINAL/'src');old=p.read_text(encoding='utf-8');new=old
            if rel.as_posix() in ('mengxu/taskscheduling/MobileDevice.java','mengxu/simulation/DynamicSimulation.java'):
                name=p.stem;anchor='public class '+name+' {'
                if new.count(anchor)!=1:raise RuntimeError('constructor overlay anchor changed')
                addition=(ROOT/f'tools/java/constructors/{name}.java.inc').read_text();new=new.replace(anchor,anchor+'\n\n'+addition,1)
            if flavor=='target' and rel.as_posix()=='mengxu/gp/function/Div.java':
                anchor='if (Double.compare(rd.value, 0) == 0)'
                if new.count(anchor)!=1:raise RuntimeError('Div overlay anchor changed')
                new=new.replace(anchor,'if (rd.value == 0.0)',1)
            if (ROOT/'tools/java/stage_d/fogsim/adapter/StageDDynamicCapture.java').exists() and rel.as_posix() in ('mengxu/taskscheduling/MobileDevice.java','mengxu/simulation/DynamicSimulation.java'):
                from java_dynamic_support import observation_overlay
                new=observation_overlay(rel.as_posix(),new).replace('fogsim.adapter.DynamicCapture.','fogsim.adapter.StageDDynamicCapture.')
            target=source/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(new,encoding='utf-8')
            if new!=old:
                patch=folder/(p.stem+'.patch');patch.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),'original/'+rel.as_posix(),'overlay/'+rel.as_posix())))
                patches.append(dict(source=rel.as_posix(),original_sha256=sha(p),overlay_sha256=sha(target),patch=patch.name,patch_sha256=sha(patch)))
        classes=folder/'classes';classes.mkdir()
        sourcepath=os.pathsep.join(map(str,(source,adapter_snapshot)))
        argv=[str(javac),'-J-Duser.language=en','-J-Dfile.encoding=UTF-8','-encoding','UTF-8','-cp',classpath,'-sourcepath',sourcepath,'-d',str(classes),*map(str,snapshot_mains)]
        start=time.time();r=subprocess.run(argv,env=env,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (folder/'javac.stdout.txt').write_text(r.stdout);(folder/'javac.stderr.txt').write_text(r.stderr)
        build=dict(argv=argv,cwd=str(ROOT),exit_code=r.returncode,duration_seconds=time.time()-start,patches=patches,
            runtime_classpath=os.pathsep.join((str(classes),classpath)),numeric_semantics_version='fogsim-gp-f64-dual-zero-v1' if flavor=='target' else 'java-original-positive-zero-v1',
            classes={p.relative_to(classes).as_posix():sha(p) for p in sorted(classes.rglob('*.class'))})
        manifest['builds'][flavor]=build;write(out/'build-manifest.json',manifest)
        if r.returncode:raise RuntimeError('compilation failed: '+str(folder/'javac.stderr.txt'))
    if any(sha(ORIGINAL/'src'/rel)!=digest for rel,digest in baseline.items()):raise RuntimeError('original sources changed')
    manifest['fingerprint']=build_fingerprint(manifest);write(out/'build-manifest.json',manifest)
    return dict(java=str(java),manifest=manifest,output=str(out))
def run_stage_d(build,input_path,output_path,*,flavor='target',main='fogsim.adapter.StageDProbe',args=None,cwd=None,timeout=45,xss='16m'):
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);java=Path(build['java']);env=environment(java)
    fingerprint=build['manifest'].get('fingerprint') or build_fingerprint(build['manifest'])
    build_sha=sha(Path(build['output'])/'build-manifest.json') if 'output' in build else 'unbound'
    argv=[str(java),'-Xss'+xss,'-Dfogsim.stage_d.source='+fingerprint,'-Dfogsim.stage_d.build='+build_sha,'-Duser.language=en','-Dfile.encoding=UTF-8','-Dfogsim.stage_d.original='+str(flavor=='original').lower(),'-cp',build['manifest']['builds'][flavor]['runtime_classpath'],main,str(Path(input_path).resolve()),*([str(out.resolve())] if args is None else list(map(str,args)))]
    start=time.time()
    try:
        r=subprocess.run(argv,cwd=cwd or ROOT,env=env,capture_output=True,text=True,timeout=timeout);row=dict(argv=argv,cwd=str(cwd or ROOT),exit_code=r.returncode,duration_seconds=time.time()-start,stdout=r.stdout,stderr=r.stderr,timed_out=False)
    except subprocess.TimeoutExpired as e:
        row=dict(argv=argv,cwd=str(cwd or ROOT),exit_code=None,duration_seconds=time.time()-start,stdout=(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else e.stdout or '',stderr=(e.stderr or b'').decode() if isinstance(e.stderr,bytes) else e.stderr or '',timed_out=True)
    row.update(environment={'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']},java_sha256=sha(java))
    write(out.with_suffix(out.suffix+'.process.json'),row);out.with_suffix(out.suffix+'.stdout.txt').write_text(row['stdout']);out.with_suffix(out.suffix+'.stderr.txt').write_text(row['stderr'])
    return row
