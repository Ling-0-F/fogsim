"""Replay prepares the existing DynamicEngine; it has no alternate event loop."""
from dataclasses import replace
from types import SimpleNamespace
from fogsim.errors import InputError, PreparationError, StateError
from fogsim.experiment_config import ReplayRunOptions, ExperimentConfig
from fogsim.environment.build import build_environment
from fogsim.input_validation import choice
from fogsim.simulation.dynamic import DynamicEngine
from .spec import ReplayInput
from .source import ReplayWorkflowSource
from .loader import load_replay_input, parse_replay_input
from fogsim.rules.factory import install_rules, validate_rules_for_environment


class ReplayEngine(DynamicEngine):
    def _snapshot(self):
        value = super()._snapshot()
        # Observation only, needed at the Java post-trigger boundary.
        if self.output_profile == 'v1' or getattr(getattr(self, 'replay_input', None), 'schema_version', None) == 1:
            value['staged_event_counts'] = {d.id: len(self.event_queue.staging_heaps[d]) for d in self.state.mobile_devices}
        return value

    def result(self):
        result = super().result()
        source = self.admission.source
        summary = result.source_summary | source.summary()
        diagnostics = result.diagnostics | dict(comparison_status='NOT_COMPARED', replay_purpose=source.purpose,
            original_reference_trajectory_eligible=source.purpose == 'verify_reference',
            coverage_status=('INPUT_COVERAGE_INSUFFICIENT' if result.reason_code == 'REPLAY_INPUT_EXHAUSTED' or
                (source.purpose == 'reuse_inputs' and result.reason_code == 'REPLAY_INPUT_DIVERGENCE') else
                'SOURCE_DIVERGED' if result.reason_code == 'REPLAY_INPUT_DIVERGENCE' else 'AVAILABLE_FOR_OBSERVED_CALLS'),
            recorded_behavior_config=self.replay_input.to_dict()['effective_config'])
        if self.output_profile == 'v2':
            inp = self.replay_input
            diagnostics['replay_rules'] = dict(recorded=inp.recorded_rule_manifest,
                active=self.prepared_rules.rule_manifest,
                migration=(dict(from_format='fogsim.dynamic-replay', from_schema_version=1,
                    mapping='legacy_fcfs_fixed_resource_to_frozen_baseline_identity',
                    original_rules=inp.to_dict()['origin']['rules'],
                    input_sha256=inp.input_sha256) if inp.schema_version == 1 else None))
        return replace(result, source_summary=summary, diagnostics=diagnostics)


def create_replay_engine(replay_input, options=None, *, purpose='verify_reference', output_profile=None):
    if type(replay_input) is not ReplayInput: raise InputError('expected ReplayInput from load/parse_replay_input')
    choice(purpose, ('verify_reference', 'reuse_inputs'), 'purpose')
    checked = parse_replay_input(replay_input.to_dict(), require_complete=False)
    if (checked.archive != replay_input.archive or checked.initial_state != replay_input.initial_state
            or checked.capture != replay_input.capture or checked.run_config != replay_input.run_config):
        raise InputError('REPLAY_INPUT_INVALID: ReplayInput fields disagree with its document')
    original = replay_input.run_config
    options = (ReplayRunOptions(trace_enabled=original.trace_enabled,
        check_invariants=original.check_invariants, edge_data_policy=original.edge_data_policy)
        if options is None else options)
    if type(options) is not ReplayRunOptions: raise InputError('expected ReplayRunOptions')
    routing = options.routing_rule or original.routing_rule
    sequencing = options.sequencing_rule or original.sequencing_rule
    active_config = replace(original, routing_rule=routing, sequencing_rule=sequencing)
    prepared = install_rules(active_config)
    recorded = replay_input.recorded_rule_manifest
    if purpose == 'verify_reference' and prepared.rule_pair_id != recorded['rule_pair_id']:
        raise InputError('verify_reference forbids changing behavior rules; choose reuse_inputs')
    env = replay_input.archive.environment
    validate_rules_for_environment(prepared, env)
    if (replay_input.schema_version == 2 and purpose == 'verify_reference'
            and options.edge_data_policy != original.edge_data_policy):
        raise InputError('verify_reference requires recorded edge_data_policy')
    profile = 'v2' if replay_input.schema_version == 2 or prepared.has_gp or output_profile == 'v2' else 'v1'
    if output_profile not in (None, 'v1', 'v2'): raise InputError('unknown result output profile')
    # Extra budgets constrain execution; they do not extend recorded coverage.
    budgets = [x for x in (original.max_events, options.max_events) if x is not None]
    config = replace(original, routing_rule=routing, sequencing_rule=sequencing,
        max_events=min(budgets) if budgets else None, check_invariants=options.check_invariants,
        trace_enabled=options.trace_enabled, edge_data_policy=options.edge_data_policy)
    initial = replay_input.initial_state
    source = ReplayWorkflowSource(replay_input, purpose=purpose)
    engine = ReplayEngine(build_environment(env), config, env, replay_input.archive.templates, source,
        initial_cutoff=initial.B, public_seed=initial.public_seed, run_index=initial.run_index,
        operation='replay_' + replay_input.to_dict()['origin']['operation'],
        prepared_rules=prepared, output_profile=profile)
    engine.replay_input = replay_input
    try:
        engine.initialize()
    except StateError as exc:
        engine._fail(exc)
        raise PreparationError(SimpleNamespace(engine=engine), engine.result()) from exc
    except Exception:
        engine.run_status, engine.stop_reason = 'FAILED', 'unexpected initialization exception (propagated)'
        raise
    return engine


def simulate_replay(replay_input, options=None, *, purpose='verify_reference', reference_path=None,
                    input_path=None, manifest_path=None, output_profile=None):
    """Execute input only, then optionally compare a separately loaded reference.

    The scheduling source never sees the reference or manifest. Supplying an
    input path also binds the optional comparison; object callers can explicitly
    supply input_path. reuse_inputs never opens the reference.
    """
    if isinstance(replay_input, str) or hasattr(replay_input, '__fspath__'):
        input_path = replay_input if input_path is None else input_path
        replay_input = load_replay_input(replay_input)
    try:
        engine = create_replay_engine(replay_input, options, purpose=purpose, output_profile=output_profile)
        if purpose == "verify_reference" and reference_path is not None and engine.output_profile == "v2" and engine.config.trace_enabled:
            from fogsim.validation.gp_observe import attach_observer
            attach_observer(engine, dynamic=True)
        result = engine.run()
    except PreparationError as exc:
        engine, result = exc.engine, exc.result
    if purpose == 'verify_reference' and reference_path is not None:
        from pathlib import Path
        from fogsim.validation.dynamic_compare import compare_dynamic_reference
        from .loader import read_replay_json
        reference_path = Path(reference_path)
        reference = read_replay_json(reference_path)
        if type(reference) is not dict: raise InputError('reference must be an object')
        manifest = Path(manifest_path) if manifest_path is not None else reference_path.with_name('manifest.json')
        if reference.get('format') == 'fogsim.gp-reference':
            from fogsim.validation.gp_compare import compare_replay_reference
            report = compare_replay_reference(engine, result, reference,
                manifest_path=manifest if manifest.is_file() else None, input_path=input_path, reference_path=reference_path)
        elif reference.get('format') == 'fogsim.dynamic-result' and reference.get('schema_version') == 2:
            from .native import compare_native_reference
            report = compare_native_reference(engine, result, reference,
                manifest_path=manifest if manifest.is_file() else None,
                input_path=input_path, reference_path=reference_path)
        else:
            if engine.output_profile == 'v2' and engine.replay_input.schema_version == 2:
                raise InputError('v2 verify requires a matching native v2 reference; Java GP reference is B06')
            report = compare_dynamic_reference(engine, result, reference,
                manifest_path=manifest if manifest.is_file() else None,
                input_path=input_path, reference_path=reference_path)
        result = replace(result, diagnostics=result.diagnostics | {'comparison': report,
            'comparison_status': report['classification']})
    return result


def simulate_replay_config(config, *, replay_input=None):
    """Single-run versioned configuration adapter; no duplicate scheduler."""
    if type(config) is not ExperimentConfig or config.mode != 'replay' or config.repeat.count != 1:
        raise InputError('expected a single-run replay ExperimentConfig')
    inp = load_replay_input(config.source.input_path) if replay_input is None else replay_input
    if type(inp) is not ReplayInput: raise InputError("expected ReplayInput")
    if config.schema_version == 1 and inp.schema_version != 1:
        raise InputError("schema_version=1 experiment requires v1 replay input")
    return simulate_replay(inp, config.run, purpose=config.source.purpose,
        input_path=config.source.input_path, reference_path=config.source.reference_path,
        output_profile=f"v{config.schema_version}")
