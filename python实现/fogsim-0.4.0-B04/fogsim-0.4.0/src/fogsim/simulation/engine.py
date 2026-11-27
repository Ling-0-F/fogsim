import math
from fogsim.config import RunConfig
from fogsim.errors import InputError, StateError, EngineUsageError, require
from fogsim.instances.fixed import parse_instance
from fogsim.model.execution import Execution
from fogsim.rules.factory import install_rules, validate_rules_for_environment
from fogsim.rules.contexts import StateView, RoutingContext, SequencingContext
from fogsim.rules.selection import choose_route, choose_next
from .state import build_state
from .events import JobArrivalEvent, TaskVisitEvent, ProcessStartEvent, ProcessFinishEvent
from .event_queue import EventQueue
from .trace import TraceRecorder, state_snapshot, event_snapshot
from .metrics import collect_result


class EventContext:
    def __init__(self, engine, current_device):
        self.engine = engine
        self.state = engine.state
        self.current_device = current_device
        self.emitted = []

    def view(self):
        return StateView.from_state(self.state)

    def emit(self, event):
        require(event.time >= self.state.clock_time, "cannot emit an event in the past")
        self.engine.event_queue.stage(event, self.current_device)
        record = dict(event_snapshot(event), staging_device=self.current_device.id)
        self.emitted.append(record)
        self.engine.trace.emitted(record)

    def choose_route(self, task, round_number=1):
        return choose_route(RoutingContext(task, tuple(task.options), self.view(), round_number),
                            self.engine.routing_rule, self.engine.trace)

    def choose_next(self, resource):
        return choose_next(SequencingContext(resource, tuple(resource.waiting_queue), self.view()),
                           self.engine.sequencing_rule, self.engine.trace)

    def after_arrival(self, workflow):
        self.engine.after_arrival(workflow, self)

    def workflow_completed(self, workflow):
        self.engine.workflow_completed(workflow)

    def dispatch(self, option):
        self.state.validate_option(option)
        task = option.task
        require(self.state.active_workflows.get(task.workflow.id) is task.workflow,
                f"cannot dispatch inactive workflow {task.workflow.id}")
        require(not task.dispatched and not task.completed and all(p.completed for p in task.parents),
                f"duplicate/ineligible dispatch {task.key}")
        time = self.state.clock_time + option.upload_time
        require(math.isfinite(time), f"upload time overflow for {task.key}")
        task.dispatched = True
        self.emit(TaskVisitEvent(time, option))
        self.engine.trace.lifecycle(option, "dispatch", self.state.clock_time)

    def visit(self, option):
        self.state.validate_option(option)
        task, resource = option.task, option.resource
        require(self.state.active_workflows.get(task.workflow.id) is task.workflow
                and task.dispatched and not task.completed, f"ineligible visit {task.key}")
        require(task.key not in self.state.executions_by_task
                and not any(o.task is task for r in self.state.resources_by_id.values() for o in r.waiting_queue),
                f"duplicate visit {task.key}")
        option.ready_time = self.state.clock_time
        self.engine.trace.lifecycle(option, "arrival", self.state.clock_time)
        if resource.available_time > self.state.clock_time or resource.pending_start is not None:
            resource.enqueue(option)
        else:
            self.reserve_start(option, self.state.clock_time)

    def reserve_start(self, option, start_time):
        self.state.validate_option(option)
        task, resource = option.task, option.resource
        require(task.dispatched and not task.completed and task.workflow.id in self.state.active_workflows,
                f"ineligible reservation {task.key}")
        require(task.key not in self.state.executions_by_task, f"duplicate execution {task.key}")
        require(resource.pending_start is None, f"resource already reserved {resource.id}")
        require(not any(o.task is task for r in self.state.resources_by_id.values() for o in r.waiting_queue),
                "remove waiting task before reservation")
        require(start_time >= max(self.state.clock_time, option.ready_time, resource.available_time),
                "start precedes arrival/clock/availability")
        execution = Execution(option, start_time)
        self.state.executions_by_task[task.key] = execution
        resource.pending_start = execution
        self.emit(ProcessStartEvent(execution))
        self.engine.trace.plan(execution)
        return execution

    def begin_execution(self, execution):
        self.state.validate_option(execution.option)
        require(self.state.executions_by_task.get(execution.task.key) is execution,
                "unregistered start execution")
        require(execution.start_time == self.state.clock_time, "start time mismatch")
        execution.resource.begin_execution(execution)
        self.emit(ProcessFinishEvent(execution))
        self.engine.trace.started(execution)

    def finish_execution(self, execution):
        self.state.validate_option(execution.option)
        task, resource, workflow = execution.task, execution.resource, execution.task.workflow
        require(self.state.executions_by_task.get(task.key) is execution, "unregistered finish execution")
        # Registered execution + its reservation consumed => actual Start occurred.
        # No scheduler read of trace and no second mutable 'started' flag.
        require(resource.pending_start is not execution, "finish before actual start")
        require(task.dispatched and not task.completed and not any(e.task is task for e in workflow.completed_executions),
                f"duplicate/ineligible finish {task.key}")
        require(self.state.clock_time == execution.finish_time, "finish time mismatch")
        task.completed = True
        workflow.completed_executions.append(execution)
        resource.completed_task_count += 1
        self.engine.trace.lifecycle(execution.option, "finish", self.state.clock_time)


class Engine:
    def __init__(self, state, config, prepared_rules=None, *, output_profile=None):
        prepared = install_rules(config, prepared_rules)
        validate_rules_for_environment(prepared, state)
        self.state, self.config = state, config
        self.prepared_rules = prepared
        self.output_profile = "v2" if prepared.has_gp or output_profile == "v2" else "v1"
        self.event_queue = EventQueue(state.mobile_devices)
        self.trace = TraceRecorder(config.trace_enabled, state,
            manifest=prepared.rule_manifest if self.output_profile == "v2" else None)
        self.routing_rule, self.sequencing_rule = prepared.routing, prepared.sequencing
        self.processed_event_count = 0
        self.run_status = "READY"
        self.stop_reason = None

    def after_arrival(self, workflow, ctx):
        """Fixed input has no follow-up source."""

    def workflow_completed(self, workflow):
        """Fixed metrics use the existing physical completion set."""

    def run(self):
        if self.run_status != "READY":
            raise EngineUsageError("Engine.run is single-use; call simulate/create_engine for a fresh run")
        self.run_status = "RUNNING"
        try:
            while self.event_queue.has_pending():
                require(self.processed_event_count < self.config.max_events, "event limit exceeded")
                event = self.event_queue.pop_next()
                producer = self.event_queue.consume_producer(event)
                require(math.isfinite(event.time) and event.time >= self.state.clock_time, "invalid/backward event time")
                self.state.clock_time = event.time
                self.processed_event_count += 1
                self.trace.begin_event(self.processed_event_count)
                ctx = EventContext(self, event.owner)
                before = state_snapshot(self.state) if self.trace.enabled else None
                error = None
                try:
                    event.trigger(ctx)
                    if self.config.check_invariants:
                        self.state.check_invariants()
                        self.event_queue.check_reservations(self.state.resources_by_id.values())
                except Exception as exc:
                    error = str(exc) if isinstance(exc, StateError) else f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    if self.trace.enabled:
                        self.trace.append(dict(event_snapshot(event), sequence=self.processed_event_count,
                            staging_device=producer.id, before=before, after=state_snapshot(self.state),
                            emitted=ctx.emitted, actions=self.trace.actions, error=error))
            require(len(self.state.completed_workflows) == len(self.state.workflows_by_id),
                    "events exhausted with unfinished workflows")
            self.state.check_invariants()
            self.run_status = "SUCCEEDED"
        except StateError as exc:
            self.run_status, self.stop_reason = "FAILED", str(exc)
        except Exception:
            self.run_status, self.stop_reason = "FAILED", "unexpected programming exception (propagated)"
            raise
        return collect_result(self)


def create_engine(spec, config=None, *, prepared_rules=None):
    config = config if config is not None else RunConfig()
    prepared = install_rules(config, prepared_rules)
    # Also validate programmatically constructed specs; no runtime state is reused.
    spec = parse_instance(spec.to_dict())
    validate_rules_for_environment(prepared, spec)
    state = build_state(spec)
    engine = Engine(state, config, prepared)
    for workflow in state.workflows_by_id.values():
        engine.event_queue.stage(JobArrivalEvent(workflow), workflow.owner_device)
    state.check_invariants()
    return engine


def simulate(spec, config=None, *, prepared_rules=None):
    return create_engine(spec, config, prepared_rules=prepared_rules).run()
