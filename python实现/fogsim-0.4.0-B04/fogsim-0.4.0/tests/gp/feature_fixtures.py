"""Real model construction with queue-operation history and finish records."""
from types import SimpleNamespace

from fogsim.model.execution import Execution
from fogsim.model.resource import MobileDevice, ResourceType, Server
from fogsim.model.task import Task, TaskOption
from fogsim.model.workflow import Workflow
from fogsim.rules.contexts import RoutingContext, SequencingContext, StateView
from .f64_oracle import bits


def option(workflow, resource, name, pt, ut=0.0, dt=0.0):
    task = Task(name, workflow)
    workflow.tasks.append(task)
    result = TaskOption(task, resource, float(pt), float(ut), float(dt))
    task.options.append(result)
    return result


def fixture(resource_type, role):
    owner = MobileDevice("M0", 0, ResourceType.MOBILE)
    other = MobileDevice("M1", 1, ResourceType.MOBILE)
    resource = owner if resource_type == ResourceType.MOBILE else Server("S0", 0, resource_type)
    resource.available_time = 40.0
    workflow = Workflow(10, owner, 5.0)
    candidate = option(workflow, resource, "A", 4, 1.5, .5)
    candidate.ready_time = 12.0
    option(workflow, resource, "B", 1)
    option(workflow, resource, "C", 1)
    finished = option(workflow, resource, "D", 1)
    finished.task.dispatched = finished.task.completed = True
    workflow.completed_executions.append(Execution(finished, 6.0))
    # Local options stay on their owner. Only servers share across devices.
    other_workflow = Workflow(11, owner if resource_type == ResourceType.MOBILE else other, 9.0)
    q0 = option(other_workflow, resource, "Q0", 2, .5, .25)
    q1 = option(other_workflow, resource, "Q1", 3, .75, .5)
    queue = [q0, q1] if role == "routing" else [q0, candidate]
    for item in queue:
        item.task.dispatched = True
        resource.enqueue(item)
    view = StateView(20.0, (owner, other, resource) if resource is not owner else (owner, other),
                     (workflow, other_workflow), ())
    context = (RoutingContext(candidate.task, (candidate,), view) if role == "routing" else
               SequencingContext(resource, tuple(queue), view))
    return SimpleNamespace(option=candidate, context=context, resource=resource,
        workflow=workflow, other_workflow=other_workflow, queue=queue)


def describe(f):
    r = f.resource
    return dict(clock_bits=bits(f.context.view.clock_time), candidate_key=f.option.key,
        role=f.context.kind.value, queue=[o.key for o in r.waiting_queue],
        resource_type=r.resource_type.value, available_bits=bits(r.available_time),
        cache_bits=[bits(r.queued_processing_time), bits(r.queued_total_time)],
        workflows=[dict(id=w.id, owner=w.owner_device.id, release_bits=bits(w.release_time),
            tasks=[dict(key=t.key, completed=t.completed, dispatched=t.dispatched,
                options=[dict(key=o.key, ready_bits=bits(o.ready_time),
                    duration_bits=[bits(o.processing_time), bits(o.upload_time), bits(o.download_time)])
                    for o in t.options]) for t in w.tasks],
            completed_records=[e.option.key for e in w.completed_executions])
            for w in f.context.view.active_workflows])
