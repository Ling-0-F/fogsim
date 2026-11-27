from dataclasses import dataclass, field
import math
from fogsim.errors import require
from fogsim.model.resource import MobileDevice, Server, ResourceType
from fogsim.model.workflow import Workflow
from fogsim.model.task import Task, TaskOption
from fogsim.instances.identity import resource_identities


@dataclass(eq=False)
class SystemState:
    clock_time: float = 0.0
    mobile_devices: list = field(default_factory=list)
    servers: list = field(default_factory=list)
    resources_by_id: dict = field(default_factory=dict)
    workflows_by_id: dict = field(default_factory=dict)
    tasks_by_key: dict = field(default_factory=dict)
    pending_arrivals: dict = field(default_factory=dict)
    active_workflows: dict = field(default_factory=dict)
    completed_workflows: dict = field(default_factory=dict)
    executions_by_task: dict = field(default_factory=dict)

    @property
    def arrived_workflow_count(self):
        return len(self.active_workflows) + len(self.completed_workflows)

    def validate_option(self, option):
        task = option.task
        require(self.tasks_by_key.get(task.key) is task, f"foreign task {task.key}")
        require(self.workflows_by_id.get(task.workflow.id) is task.workflow, "foreign workflow")
        require(self.resources_by_id.get(option.resource.id) is option.resource, "foreign resource")
        require(any(o is option for o in task.options), "foreign option")

    def validate_new_workflow(self, workflow):
        require(workflow.id not in self.workflows_by_id, "duplicate workflow ID")
        require(self.resources_by_id.get(workflow.owner_device.id) is workflow.owner_device,
                "foreign workflow owner")
        require(bool(workflow.tasks) and len({t.id for t in workflow.tasks}) == len(workflow.tasks),
                "empty/duplicate workflow tasks")
        for task in workflow.tasks:
            require(task.workflow is workflow and task.key not in self.tasks_by_key,
                    "new task identity/index conflict")
            require(not task.dispatched and not task.completed, "new task already executed")
            for option in task.options:
                require(option.task is task and self.resources_by_id.get(option.resource.id) is option.resource,
                        "new option identity conflict")

    def register_workflow(self, workflow):
        self.validate_new_workflow(workflow)
        self.workflows_by_id[workflow.id] = workflow
        self.tasks_by_key.update((t.key, t) for t in workflow.tasks)
        self.pending_arrivals[workflow.id] = workflow

    def activate_workflow(self, workflow):
        require(self.pending_arrivals.get(workflow.id) is workflow, "duplicate/foreign arrival")
        require(self.clock_time == workflow.release_time, "arrival time mismatch")
        del self.pending_arrivals[workflow.id]
        self.active_workflows[workflow.id] = workflow

    def register_completion(self, workflow):
        require(self.workflows_by_id.get(workflow.id) is workflow, "foreign completion workflow")
        records = workflow.completed_executions
        valid_records = (bool(records) and len(records) == len(workflow.tasks)
                         and {e.task for e in records} == set(workflow.tasks)
                         and all(self.executions_by_task.get(e.task.key) is e and e.task.completed
                                 for e in records))
        if workflow.completion_registered or workflow.id in self.completed_workflows:
            require(workflow.completion_registered and self.completed_workflows.get(workflow.id) is workflow
                    and workflow.is_done and workflow.id not in self.active_workflows
                    and workflow.id not in self.pending_arrivals and valid_records
                    and workflow.completion_time == max(e.finish_time for e in records),
                    "inconsistent completion registration")
            return False
        require(self.active_workflows.get(workflow.id) is workflow and workflow.is_done,
                "cannot register incomplete/inactive workflow")
        require(valid_records, "inconsistent completed executions")
        completion = max(e.finish_time for e in records)
        require(completion == self.clock_time, "completion time mismatch")
        workflow.completion_time = completion
        del self.active_workflows[workflow.id]
        self.completed_workflows[workflow.id] = workflow
        workflow.completion_registered = True
        return True

    def check_invariants(self):
        partitions = [set(x) for x in (self.pending_arrivals, self.active_workflows, self.completed_workflows)]
        require(set.union(*partitions) == set(self.workflows_by_id)
                and sum(map(len, partitions)) == len(self.workflows_by_id), "workflow partition broken")
        completed = 0
        for w in self.workflows_by_id.values():
            require(w.completion_registered == (w.id in self.completed_workflows), "registration flag mismatch")
            records = w.completed_executions
            require(len({e.task for e in records}) == len(records), "duplicate completion record")
            require(len(records) == sum(t.completed for t in w.tasks), "task/record count mismatch")
            if w.completion_registered:
                require(w.is_done and w.completion_time == max(e.finish_time for e in records), "invalid completed workflow")
            else:
                require(w.completion_time is None, "unregistered completion time")
            for t in w.tasks:
                require(self.tasks_by_key.get(t.key) is t and t.workflow is w, "task identity mismatch")
                require(not t.completed or t.dispatched, "completed task was not dispatched")
                require(w.id not in self.pending_arrivals or not t.dispatched, "future task dispatched")
                for child in t.children:
                    require(t in child.parents and child.workflow is w, "broken child edge")
                for parent in t.parents:
                    require(t in parent.children and parent.workflow is w, "broken parent edge")
                for o in t.options:
                    self.validate_option(o)
            for ex in records:
                require(self.executions_by_task.get(ex.task.key) is ex and ex.task.completed, "completion identity mismatch")
            completed += len(records)
        require(completed == sum(r.completed_task_count for r in self.resources_by_id.values()), "resource completion count mismatch")
        for r in self.resources_by_id.values():
            require(r.completed_task_count == sum(e.resource is r for w in self.workflows_by_id.values()
                                                  for e in w.completed_executions),
                    f"completion count mismatch on {r.id}")
            q = r.waiting_queue
            require(len({o.task for o in q}) == len(q), "duplicate queued task")
            for o in q:
                self.validate_option(o)
                require(o.resource is r and o.task.dispatched and not o.task.completed
                        and o.task.key not in self.executions_by_task and o.ready_time <= self.clock_time,
                        "invalid queue membership")
            for actual, expected in (
                (r.queued_processing_time, sum(o.processing_time for o in q)),
                (r.queued_total_time, sum((o.processing_time + o.upload_time + o.download_time) for o in q))):
                require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9), "queue cache mismatch")
            if r.resource_type != ResourceType.MOBILE and not q:
                require(r.queued_processing_time == 0 and r.queued_total_time == 0, "server empty cache not zero")
            if r.pending_start is not None:
                ex = r.pending_start
                require(ex.resource is r and self.executions_by_task.get(ex.task.key) is ex
                        and not ex.task.completed and ex.start_time >= self.clock_time, "invalid pending start")
            executions = sorted((e for e in self.executions_by_task.values() if e.resource is r),
                                key=lambda e: e.start_time)
            require(all(a.finish_time <= b.start_time for a, b in zip(executions, executions[1:])),
                    f"overlapping executions on {r.id}")


def build_state(spec):
    state = SystemState()
    mobile = [r for r in spec.resources if r.type == "MOBILE"]
    servers = [r for kind in ("EDGE", "CLOUD") for r in spec.resources if r.type == kind]
    objects = {}
    identities = {r.id: r.numeric_id for r in resource_identities(spec.resources)}
    for r in mobile:
        obj = MobileDevice(r.id, identities[r.id], ResourceType.MOBILE, can_process_tasks=r.can_process_tasks)
        state.mobile_devices.append(obj); objects[r.id] = obj
    for r in servers:
        obj = Server(r.id, identities[r.id], ResourceType(r.type))
        state.servers.append(obj); objects[r.id] = obj
    state.resources_by_id = {r.id: objects[r.id] for r in spec.resources}
    for w in spec.workflows:
        workflow = Workflow(w.id, objects[w.owner_device_id], w.release_time)
        state.workflows_by_id[w.id] = workflow
        state.pending_arrivals[w.id] = workflow
        for t in w.tasks:
            task = Task(t.id, workflow)
            workflow.tasks.append(task); state.tasks_by_key[task.key] = task
            for o in t.options:
                task.options.append(TaskOption(task, objects[o.resource_id], o.processing_time, o.upload_time, o.download_time))
        for a, b in w.dependencies:
            parent, child = state.tasks_by_key[w.id, a], state.tasks_by_key[w.id, b]
            parent.children.append(child); child.parents.append(parent)
    return state
