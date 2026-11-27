import argparse
import json
from dataclasses import replace
from pathlib import Path
from fogsim import RunConfig, load_fixed_instance, simulate, __version__
from fogsim.config import load_config
from fogsim.errors import InputError
from fogsim.io import write_json_atomic


def _fixed_main(argv=None):
    parser = argparse.ArgumentParser(description=f"Fog workflow simulator {__version__}",
                                     epilog="New commands: dynamic --help; replay --help; export-fixed --help")
    parser.add_argument("--version", action="version", version=__version__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=Path)
    group.add_argument("--instance", type=Path)
    parser.add_argument("--fixed-resource", help="debug route target; default FCFS")
    parser.add_argument("--no-trace", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeat", type=int, default=1, help="fresh object graph on every run")
    args = parser.parse_args(argv)
    protected = {p.resolve() for p in (args.config,args.instance) if p is not None}
    try:
        if args.output is not None and args.output.resolve() in protected:
            raise InputError("output must not overwrite an input/config file")
        if args.config is not None:
            _protect_config_sources(args.config,protected,experiment=False)
        if args.repeat < 1:
            raise InputError("repeat must be positive")
        path, config = load_config(args.config) if args.config else (args.instance, RunConfig())
        if args.fixed_resource:
            config = replace(config, routing_kind="fixed_resource", fixed_resource_id=args.fixed_resource,
                             routing_expression=None)
        if args.no_trace:
            config = replace(config, trace_enabled=False)
        protected.add(path.resolve())
        _clear_output(args.output,protected)
        spec = load_fixed_instance(path)
        results = [simulate(spec, config).to_dict() for _ in range(args.repeat)]
        output = results[0] if args.repeat == 1 else {"runs": results, "identical": all(r == results[0] for r in results)}
        text = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            write_json_atomic(args.output,output)
            print(json.dumps({"output": str(args.output), "status": results[-1]["status"],
                              "makespan": results[-1]["makespan"], "runs": args.repeat}, ensure_ascii=False))
        else:
            print(text)
        return 0 if all(r["status"] == "SUCCEEDED" for r in results) else 1
    except InputError as exc:
        _clear_output(args.output,protected,allow_protected=True)
        parser.exit(2, f"input error: {exc}\n")
    except BaseException:
        _clear_output(args.output,protected,allow_protected=True)
        raise


def _clear_output(path, protected, *, allow_protected=False):
    if path is None: return
    if _is_protected(path,protected):
        if allow_protected: return
        raise InputError("output must not overwrite an input/config/reference file")
    if path.is_file() or path.is_symlink(): path.unlink()


def _config_from_args(args):
    from .instances.fixed import read_json
    from .experiment_config import parse_experiment_config
    if args.config is not None:
        raw = read_json(args.config)
        base = args.config.resolve().parent
    else:
        purpose = args.purpose or ('verify_reference' if args.reference is not None else 'reuse_inputs')
        raw = dict(format='fogsim.experiment',schema_version=1,mode='replay',
                   source=dict(input_path=str(args.input.resolve()),purpose=purpose))
        if args.reference is not None:raw['source']['reference_path']=str(args.reference.resolve())
        base = Path.cwd()
    if not isinstance(raw,dict) or raw.get('mode')!=args.command:
        raise InputError('configuration mode must match the explicit command')
    # Modify the JSON before parsing, retaining the distinction between an
    # explicit repeat mode and a single-run default expanded by the parser.
    from copy import deepcopy
    raw = deepcopy(raw)
    if not isinstance(raw.get('source'),dict): raise InputError('source must be an object')
    raw.setdefault('run',{});raw.setdefault('repeat',{});raw.setdefault('output',{})
    if not all(isinstance(raw[k],dict) for k in ('run','repeat','output')):
        raise InputError('run/repeat/output must be objects')
    if getattr(args,'seed',None) is not None:raw['source']['seed']=args.seed
    if getattr(args,'purpose',None) is not None:raw['source']['purpose']=args.purpose
    if getattr(args,'reference',None) is not None:raw['source']['reference_path']=str(args.reference.resolve())
    for name,key in (('repeat','count'),('repeat_mode','mode'),('seeds','seeds')):
        value=getattr(args,name,None)
        if value is not None:raw['repeat'][key]=value
    if args.no_trace:raw['run']['trace_enabled']=False
    if args.max_events is not None:raw['run']['max_events']=args.max_events
    if args.edge_data_policy is not None:raw['run']['edge_data_policy']=args.edge_data_policy
    if args.fixed_resource is not None:raw['run']['routing_rule']=dict(kind='fixed_resource',resource_id=args.fixed_resource)
    if args.dataset_role is not None:raw['output']['dataset_role']=args.dataset_role
    return parse_experiment_config(raw,base_dir=base)


def _new_parser(command):
    parser=argparse.ArgumentParser(prog='fogsim '+command,description='Versioned '+command+' entry')
    if command=='export-fixed':
        parser.add_argument('--input',required=True,type=Path)
        parser.add_argument('--output',required=True,type=Path)
        parser.add_argument('--manifest',type=Path,help='default: OUTPUT stem + .projection.json')
        return parser
    if command=='dynamic':parser.add_argument('--config',required=True,type=Path)
    else:
        source=parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--config',type=Path);source.add_argument('--input',type=Path)
        parser.add_argument('--reference',type=Path)
        parser.add_argument('--purpose',choices=('verify_reference','reuse_inputs'))
    if command=='dynamic':
        parser.add_argument('--seed',type=int)
        parser.add_argument('--repeat-mode',choices=('fresh_same_seed','fresh_seed_list','java_rerun'))
        parser.add_argument('--seeds',type=int,nargs='+')
    parser.add_argument('--repeat',type=int)
    parser.add_argument('--no-trace',action='store_true')
    parser.add_argument('--max-events',type=int)
    parser.add_argument('--edge-data-policy',choices=('retain','release_after_materialization'))
    parser.add_argument('--fixed-resource')
    parser.add_argument('--dataset-role',choices=('debug','train','test'))
    parser.add_argument('--output',type=Path)
    parser.add_argument('--archive-dir',type=Path,help='also save each standalone input.json')
    return parser


def _new_main(command, argv):
    from .experiments import run_experiment
    from .replay import load_replay_input,export_fixed_instance,fixed_projection_metadata
    import hashlib
    parser=_new_parser(command);args=parser.parse_args(argv);args.command=command
    protected={p.resolve() for p in (getattr(args,'config',None),getattr(args,'input',None),getattr(args,'reference',None)) if p is not None}
    latest=None
    try:
        if command=='export-fixed':
            manifest=args.manifest or args.output.with_suffix('.projection.json')
            if manifest.resolve()==args.output.resolve():raise InputError('manifest and fixed output must differ')
            _clear_output(args.output,protected);_clear_output(manifest,protected)
            inp=load_replay_input(args.input);spec=export_fixed_instance(inp)
            meta=fixed_projection_metadata(inp) | dict(format='fogsim.fixed-projection',schema_version=1,complete=False,
                      source_input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest())
            write_json_atomic(manifest,meta);write_json_atomic(args.output,spec.to_dict())
            meta.update(complete=True,fixed_input_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
            write_json_atomic(manifest,meta)
            print(json.dumps(dict(status='SUCCEEDED',kind='fixed_projection',output=str(args.output),manifest=str(manifest))))
            return 0
        if args.config is not None:
            _protect_config_sources(args.config,protected,experiment=True)
        config=_config_from_args(args)
        if config.mode=='replay':
            protected.add(config.source.input_path.resolve())
            if config.source.reference_path is not None:protected.add(config.source.reference_path.resolve())
        _clear_output(args.output,protected)
        direct_v2 = config.schema_version == 2 and config.repeat.count == 1 and args.archive_dir is None
        def checkpoint(result):
            nonlocal latest
            latest=(result.runs[0].to_dict() if direct_v2 and result.runs else result.to_dict())
            if args.archive_dir is not None:
                for i,inp in enumerate(result.input_archives):
                    if inp is None:continue
                    path=args.archive_dir/f'run-{i:06d}.input.json'
                    if _is_protected(path,protected):raise InputError('archive output would overwrite source input')
                    if args.output is not None and path.resolve()==args.output.resolve():raise InputError('archive/result output collision')
                    write_json_atomic(path,inp.to_dict())
            if args.archive_dir is not None:
                manifest=args.archive_dir/'batch-manifest.json'
                if _is_protected(manifest,protected) or (args.output is not None and manifest.resolve()==args.output.resolve()):
                    raise InputError('archive manifest would overwrite input/result')
                write_json_atomic(manifest,dict(format='fogsim.batch-input-manifest',schema_version=config.schema_version,
                    batch_complete=result.batch_complete,planned_runs=result.planned_runs,
                    files=[f'run-{i:06d}.input.json' for i,inp in enumerate(result.input_archives) if inp is not None],
                    **({'inputs': [dict(path=f'run-{i:06d}.input.json',
                        sha256=hashlib.sha256((args.archive_dir/f'run-{i:06d}.input.json').read_bytes()).hexdigest(),
                        rule_pair_id=inp.recorded_rule_manifest['rule_pair_id'])
                        for i,inp in enumerate(result.input_archives) if inp is not None]} if config.schema_version == 2 else {})))
            if args.output is not None:write_json_atomic(args.output,latest)
        try:
            result=run_experiment(config,on_progress=checkpoint)
        except BaseException as exc:
            if latest is not None and args.output is not None:
                latest.update(batch_complete=False,status='INCOMPLETE',all_runs_mean=None,
                              interruption=dict(type=type(exc).__name__,message=str(exc)))
                write_json_atomic(args.output,latest)
            raise
        if args.output is None:print(json.dumps(latest,ensure_ascii=False,indent=2,allow_nan=False))
        else:print(json.dumps(dict(output=str(args.output),status=result.status,runs=len(result.runs),
                                   succeeded_runs=result.succeeded_runs,failed_runs=result.failed_runs,not_run=result.not_run)))
        return 0 if result.status=='SUCCEEDED' else 1
    except InputError as exc:
        if latest is None:_clear_output(args.output,protected,allow_protected=True)
        parser.exit(2,f'input error: {exc}\n')
    except BaseException:
        if latest is None:_clear_output(args.output,protected,allow_protected=True)
        raise


def main(argv=None):
    import sys
    args=list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ('dynamic','replay','export-fixed'):
        return _new_main(args[0],args[1:])
    return _fixed_main(args)


def _protect_config_sources(path, protected, *, experiment):
    from .instances.fixed import read_json
    raw=read_json(path)
    if not isinstance(raw,dict):return
    source=raw.get('source') if experiment else raw
    if not isinstance(source,dict):return
    for key in ('input_path','reference_path','dag_root') if experiment else ('instance',):
        value=source.get(key)
        if isinstance(value,str) and value:
            protected.add((path.resolve().parent/value).resolve())


def _is_protected(path, protected):
    resolved=path.resolve()
    return any(resolved==source or (source.is_dir() and resolved.is_relative_to(source)) for source in protected)
