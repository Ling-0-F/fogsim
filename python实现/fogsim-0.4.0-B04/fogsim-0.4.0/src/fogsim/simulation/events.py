"""Constructors are pure. All mutations occur through trigger/EventContext."""
from dataclasses import dataclass
from .readiness import ready_tasks


@dataclass(eq=False, frozen=True)
class JobArrivalEvent:
    workflow: object

    @property
    def time(self):
        return self.workflow.release_time

    @property
    def owner(self):
        return self.workflow.owner_device

    def trigger(self, ctx):
        ctx.state.activate_workflow(self.workflow)
        for task in ready_tasks(self.workflow, ctx.view()):
            for option in task.options:
                option.ready_time = self.workflow.release_time
            ctx.dispatch(ctx.choose_route(task))
        ctx.after_arrival(self.workflow)


@dataclass(eq=False, frozen=True)
class TaskVisitEvent:
    time: float
    option: object

    @property
    def owner(self):
        return self.option.task.workflow.owner_device

    def trigger(self, ctx):
        ctx.visit(self.option)


@dataclass(eq=False, frozen=True)
class ProcessStartEvent:
    execution: object

    @property
    def time(self):
        return self.execution.start_time

    @property
    def owner(self):
        return self.execution.task.workflow.owner_device

    def trigger(self, ctx):
        ctx.begin_execution(self.execution)


@dataclass(eq=False, frozen=True)
class ProcessFinishEvent:
    execution: object

    @property
    def time(self):
        return self.execution.finish_time

    @property
    def owner(self):
        return self.execution.task.workflow.owner_device

    def trigger(self, ctx):
        ctx.finish_execution(self.execution)
        resource = self.execution.resource
        if resource.waiting_queue and resource.pending_start is None:
            option = ctx.choose_next(resource)  # Score while still queued.
            resource.remove_waiting(option)
            ctx.reserve_start(option, max(resource.available_time, ctx.state.clock_time))
        workflow = self.execution.task.workflow
        ready = ready_tasks(workflow, ctx.view())
        if ready:
            # Java getNextDag wrapper is called twice: A,B,A,B, then dispatch.
            for round_number in (1, 2):
                selected = [ctx.choose_route(t, round_number) for t in ready]
            for option in selected:
                ctx.dispatch(option)
        elif workflow.is_done:
            if ctx.state.register_completion(workflow):
                ctx.workflow_completed(workflow)
