package fogsim.adapter;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import mengxu.algorithm.FCFS;
import mengxu.rule.AbstractRule;
import mengxu.rule.RuleType;
import mengxu.simulation.*;
import mengxu.simulation.event.*;
import mengxu.simulation.state.SystemState;
import mengxu.taskscheduling.*;
import mengxu.taskscheduling.Process;

/** Fixed-data bootstrap and observers around the original Java scheduling classes.
 * No trigger, compareTo, priorTo, queue or canAddToQueue method is rewritten.
 */
public final class FixedInstanceMain {
    final SystemState state = new SystemState();
    final List<Job> jobs = new ArrayList<>();
    final List<Task> tasks = new ArrayList<>();
    final List<Object> resources = new ArrayList<>();
    final Map<Integer,Job> jobsById = new LinkedHashMap<>();
    final Map<String,Object> resourcesById = new LinkedHashMap<>();
    final IdentityHashMap<Task,String> taskNames = new IdentityHashMap<>();
    final IdentityHashMap<Object,String> resourceNames = new IdentityHashMap<>();
    final IdentityHashMap<JobArrivalEvent,Job> arrivals = new IdentityHashMap<>();
    final IdentityHashMap<AbstractEvent,FixedDevice> producers = new IdentityHashMap<>();
    final Set<Integer> pendingArrivals = new LinkedHashSet<>();
    final List<Object> events = new ArrayList<>();
    final List<Object> decisions = new ArrayList<>();
    final IdentityHashMap<Task,Map<String,Object>> taskRows = new IdentityHashMap<>();
    // Observers only: these collections are NEVER read by Java scheduling methods.
    final List<Process> acceptedPlans = new ArrayList<>();
    final IdentityHashMap<Object,List<Process>> observedPending = new IdentityHashMap<>();
    final IdentityHashMap<Task,Integer> routeRounds = new IdentityHashMap<>();
    final List<Object> anomalies = new ArrayList<>();
    final List<Object> reservationChecks = new ArrayList<>();
    final Map<String,Object> request;
    final Map<String,Object> config;
    final boolean detailed;
    final long maxEvents;
    final ObservedRule routing;
    final ObservedRule sequencing;
    final FixedSimulation simulation;
    Map<String,Object> frame;
    int processed;
    int suppressedGenerationCalls;
    int decisionSequence;
    String status = "READY";
    String reason;

    static Map<String,Object> map(Object... entries) {
        Map<String,Object> result = new LinkedHashMap<>();
        for (int i = 0; i < entries.length; i += 2) result.put((String) entries[i], entries[i + 1]);
        return result;
    }
    @SuppressWarnings("unchecked") static Map<String,Object> obj(Object value) {
        if (!(value instanceof Map)) throw new IllegalArgumentException("expected JSON object");
        return (Map<String,Object>) value;
    }
    @SuppressWarnings("unchecked") static List<Object> list(Object value) {
        if (!(value instanceof List)) throw new IllegalArgumentException("expected JSON array");
        return (List<Object>) value;
    }
    static String str(Object value) {
        if (!(value instanceof String) || ((String) value).isEmpty()) throw new IllegalArgumentException("expected nonempty string");
        return (String) value;
    }
    static double time(Object value, boolean positive) {
        if (!(value instanceof Number)) throw new IllegalArgumentException("expected numeric time");
        double number = ((Number) value).doubleValue();
        if (!Double.isFinite(number) || (positive ? number <= 0 : number < 0))
            throw new IllegalArgumentException("invalid time " + value);
        return number;
    }
    static int integer(Object value) {
        if (!(value instanceof Long) || (Long) value < Integer.MIN_VALUE || (Long) value > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Java workflow ID must fit signed int32");
        return ((Long) value).intValue();
    }
    static void check(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    FixedInstanceMain(Map<String,Object> request) {
        this.request = request;
        check(((Number) request.get("schema_version")).intValue() == 1, "unsupported request schema");
        this.config = obj(request.get("config"));
        this.detailed = !Boolean.FALSE.equals(request.get("record_trace"));
        this.maxEvents = ((Number) config.get("max_events")).longValue();
        check(maxEvents > 0, "invalid max_events");
        check("java_compatible".equals(config.get("event_policy")), "unsupported event policy");
        check("fcfs".equals(config.get("sequencing_kind")), "only FCFS sequencing supported");
        check(List.of("fcfs", "fixed_resource").contains(config.get("routing_kind")), "unsupported routing rule");
        routing = new ObservedRule(RuleType.ROUTING);
        sequencing = new ObservedRule(RuleType.SEQUENCING);
        simulation = new FixedSimulation();
        build(obj(request.get("input")));
    }

    void build(Map<String,Object> input) {
        check("s".equals(input.get("time_unit")), "time unit must be seconds");
        List<Object> resourceInput = list(input.get("resources"));
        int mobileId = 0, serverId = 0;
        for (Object value : resourceInput) {
            Map<String,Object> r = obj(value);
            if (!"MOBILE".equals(r.get("type"))) continue;
            FixedDevice device = new FixedDevice(mobileId++);
            Object can = r.getOrDefault("can_process_tasks", Boolean.TRUE);
            check(can instanceof Boolean, "invalid can_process_tasks");
            device.setCanProcessTask((Boolean) can);
            device.setSimulation(simulation);
            state.addMobileDevice(device);
            registerResource(str(r.get("id")), device);
        }
        for (String type : List.of("EDGE", "CLOUD")) {
            for (Object value : resourceInput) {
                Map<String,Object> r = obj(value);
                if (!type.equals(r.get("type"))) continue;
                // Rate/bandwidth placeholders are unused by FCFS and direct duration inputs.
                Server server = new Server(serverId++, ServerType.valueOf(type), 1.0, 1.0, 1.0);
                state.addServer(server);
                registerResource(str(r.get("id")), server);
            }
        }
        for (Object value : resourceInput) {
            Object resource = resourcesById.get(str(obj(value).get("id")));
            check(resource != null, "unknown resource type");
            resources.add(resource);
            observedPending.put(resource, new ArrayList<>());
        }
        check(!state.getMobileDevices().isEmpty(), "no mobile devices");
        for (Object value : list(input.get("workflows"))) {
            Map<String,Object> w = obj(value);
            int id = integer(w.get("id"));
            check(!jobsById.containsKey(id), "duplicate workflow ID");
            Object owner = resourcesById.get(str(w.get("owner_device_id")));
            check(owner instanceof FixedDevice, "invalid workflow owner");
            List<Task> jobTasks = new ArrayList<>();
            Job job = new Job(id, time(w.get("release_time"), false), 1.0, (FixedDevice) owner, jobTasks, JobType.DAG);
            jobs.add(job); jobsById.put(id, job); pendingArrivals.add(id);
            Map<String,Task> byName = new LinkedHashMap<>();
            for (Object taskValue : list(w.get("tasks"))) {
                Map<String,Object> t = obj(taskValue);
                String name = str(t.get("id"));
                check(!byName.containsKey(name), "duplicate task ID");
                Task task = new Task(jobTasks.size());
                task.setJob(job); jobTasks.add(task); tasks.add(task);
                taskNames.put(task, name); byName.put(name, task);
                List<Object> eligible = new ArrayList<>();
                if (((FixedDevice) owner).isCanProcessTask()) eligible.add(owner);
                eligible.addAll(state.getServers());
                Map<String,Object> durations = obj(t.get("execution_times"));
                check(!eligible.isEmpty() && durations.size() == eligible.size(), "candidate set mismatch");
                for (Object resource : eligible) {
                    Map<String,Object> times = obj(durations.get(resourceNames.get(resource)));
                    double pt = time(times.get("processing_time"), true);
                    double ut = time(times.get("upload_time"), false);
                    double dt = time(times.get("download_time"), false);
                    TaskOption option;
                    if (resource instanceof FixedDevice) {
                        check(ut == 0 && dt == 0, "local communication must be zero");
                        option = new TaskOption(task, (MobileDevice) resource, pt, ut, dt);
                    } else option = new TaskOption(task, (Server) resource, pt, ut, dt);
                    task.addTaskOption(option);
                }
                if ("fixed_resource".equals(config.get("routing_kind")))
                    check(durations.containsKey(str(config.get("fixed_resource_id"))), "fixed target ineligible");
                taskRows.put(task, map("workflow_id", id, "task_id", name, "resource_id", null,
                    "dispatch_time", null, "arrival_time", null, "start_time", null,
                    "compute_finish_time", null, "finish_time", null, "plan", null));
            }
            check(!jobTasks.isEmpty(), "empty workflow");
            Set<String> edges = new HashSet<>();
            for (Object edgeValue : list(w.get("dependencies"))) {
                List<Object> edge = list(edgeValue);
                check(edge.size() == 2, "invalid dependency");
                Task a = byName.get(str(edge.get(0))), b = byName.get(str(edge.get(1)));
                check(a != null && b != null && a != b && edges.add(a.getId() + ":" + b.getId()), "invalid dependency");
                a.getChildTaskList().add(b); b.getParentTaskList().add(a);
            }
            // Loading is also validated by the Python fixed-instance parser before Java launch.
            int[] degree = new int[jobTasks.size()];
            ArrayDeque<Task> todo = new ArrayDeque<>();
            for (Task t : jobTasks) { degree[t.getId()] = t.getParentTaskList().size(); if (degree[t.getId()] == 0) todo.add(t); }
            int visited = 0;
            while (!todo.isEmpty()) { Task t = todo.remove(); visited++; for (Task c : t.getChildTaskList()) if (--degree[c.getId()] == 0) todo.add(c); }
            check(visited == jobTasks.size(), "dependency cycle");
            JobArrivalEvent event = new JobArrivalEvent(job, job.getMobileDevice());
            arrivals.put(event, job);
            ((FixedDevice) owner).addEvent(event);
        }
        check(!jobs.isEmpty(), "empty input");
    }

    void registerResource(String id, Object resource) {
        check(!resourcesById.containsKey(id), "duplicate resource ID");
        resourcesById.put(id, resource); resourceNames.put(resource, id);
    }
    Object resource(TaskOption option) { return option.getServer() == null ? option.getTask().getJob().getMobileDevice() : option.getServer(); }
    List<Object> taskKey(Task task) { return List.of(task.getJob().getId(), taskNames.get(task)); }
    List<Object> optionKey(TaskOption option) { return List.of(option.getTask().getJob().getId(), taskNames.get(option.getTask()), resourceNames.get(resource(option))); }
    List<TaskOption> queue(Object resource) { return resource instanceof MobileDevice ? ((MobileDevice) resource).getQueue() : ((Server) resource).getQueue(); }
    double available(Object resource) { return resource instanceof MobileDevice ? ((MobileDevice) resource).getReadyTime() : ((Server) resource).getReadyTime(); }
    double wiq(Object resource) { return resource instanceof MobileDevice ? ((MobileDevice) resource).totalProcTimeInQueue() : ((Server) resource).totalProcTimeInQueue(); }
    double ttiq(Object resource) { return resource instanceof MobileDevice ? ((MobileDevice) resource).totalProcTimeAndUpLoadAndDownLoadTimeInQueue() : ((Server) resource).totalProcTimeAndUpLoadAndDownLoadTimeInQueue(); }

    Map<String,Object> eventSnapshot(AbstractEvent event) {
        TaskOption option = null;
        Job job;
        if (event instanceof TaskVisitEvent) option = ((TaskVisitEvent) event).getOperationOption();
        else if (event instanceof ProcessStartEvent) option = ((ProcessStartEvent) event).getProcess().getTaskOption();
        else if (event instanceof ProcessFinishEvent) option = ((ProcessFinishEvent) event).getProcess().getTaskOption();
        if (option != null) job = option.getTask().getJob();
        else { job = arrivals.get(event); check(job != null, "unknown arrival event"); }
        return map("type", event.getClass().getSimpleName(), "time", event.getTime(),
            "owner", resourceNames.get(event.getMobileDevice()), "workflow_id", job.getId(),
            "task_id", option == null ? null : taskNames.get(option.getTask()),
            "resource_id", option == null ? null : resourceNames.get(resource(option)));
    }

    void lifecycle(TaskOption option, String action, double time) {
        Map<String,Object> row = taskRows.get(option.getTask());
        if (row.get(action + "_time") != null)
            anomalies.add(map("kind", "duplicate_" + action, "task", taskKey(option.getTask()), "time", time));
        row.put("resource_id", resourceNames.get(resource(option)));
        row.put(action + "_time", time);
    }

    void emitted(AbstractEvent event, FixedDevice producer) {
        producers.put(event, producer);
        if (event instanceof TaskVisitEvent) lifecycle(((TaskVisitEvent) event).getOperationOption(), "dispatch", state.getClockTime());
        if (event instanceof ProcessStartEvent) {
            Process p = ((ProcessStartEvent) event).getProcess();
            acceptedPlans.add(p); observedPending.get(resource(p.getTaskOption())).add(p);
            taskRows.get(p.getTaskOption().getTask()).put("plan", map("start_time", p.getStartTime(),
                "compute_finish_time", p.getStartTime() + p.getTaskOption().getProcTime(), "finish_time", p.getFinishTime()));
        }
        if (detailed && frame != null) {
            Map<String,Object> record = eventSnapshot(event);
            record.put("staging_device", resourceNames.get(producer));
            list(frame.get("emitted")).add(record);
            list(frame.get("actions")).add(map("kind", "EMIT", "event", record));
        }
    }

    List<Object> resourceSnapshot(boolean decision) {
        List<Object> result = new ArrayList<>();
        for (Object r : resources) {
            List<Object> waiting = new ArrayList<>(), pending = new ArrayList<>();
            for (TaskOption option : queue(r)) waiting.add(optionKey(option));
            for (Process p : observedPending.get(r)) pending.add(taskKey(p.getTaskOption().getTask()));
            Map<String,Object> row = map("id", resourceNames.get(r), "available_time", available(r),
                decision ? "queue" : "waiting_queue", waiting, "queued_processing_time", wiq(r), "queued_total_time", ttiq(r));
            if (!decision) {
                row.put("numeric_id", r instanceof MobileDevice ? ((MobileDevice) r).getId() : ((Server) r).getId());
                row.put("type", r instanceof MobileDevice ? "MOBILE" : ((Server) r).getType().toString());
                row.put("observed_pending_starts", pending);
                row.put("completed_task_count", r instanceof MobileDevice ? ((MobileDevice) r).getNumTasksCompleted() : ((Server) r).getNumTasksCompleted());
            }
            result.add(row);
        }
        return result;
    }

    Map<String,Object> snapshot() {
        List<Object> taskStates = new ArrayList<>(), workflowStates = new ArrayList<>(), plans = new ArrayList<>();
        for (Task task : tasks) {
            List<Object> options = new ArrayList<>();
            for (TaskOption option : task.getTaskOptions()) options.add(map("resource_id", resourceNames.get(resource(option)),
                "ready_time", option.getReadyTime(), "priority", option.getPriority()));
            taskStates.add(map("key", taskKey(task), "dispatched", task.isDispatch(), "completed", task.isComplete(), "options", options));
        }
        for (Job job : jobs) {
            List<Object> completed = new ArrayList<>();
            for (ProcessFinishEvent event : job.getProcessFinishEvents()) completed.add(taskNames.get(event.getProcess().getTaskOption().getTask()));
            workflowStates.add(map("id", job.getId(), "completion_registered", job.isHasAddToCompletedList(),
                "completion_time", job.getCompletionTime(), "completed_tasks", completed)); // raw Java default remains 0.0
        }
        for (Process p : acceptedPlans) plans.add(map("task", taskKey(p.getTaskOption().getTask()),
            "resource_id", resourceNames.get(resource(p.getTaskOption())), "planned_start_time", p.getStartTime(),
            "planned_compute_finish_time", p.getStartTime() + p.getTaskOption().getProcTime(), "planned_finish_time", p.getFinishTime()));
        return map("clock_time", state.getClockTime(), "pending_arrivals", new ArrayList<>(pendingArrivals),
            "active_workflows", state.getJobsInSystem().stream().map(Job::getId).toList(),
            "completed_workflows", state.getJobsCompleted().stream().map(Job::getId).toList(),
            "tasks", taskStates, "resources", resourceSnapshot(false), "executions", plans, "workflows", workflowStates);
    }

    Map<String,Object> result() {
        List<Object> work = new ArrayList<>(), rows = new ArrayList<>();
        double first = Double.POSITIVE_INFINITY, last = 0;
        for (Job job : jobs) {
            boolean complete = job.isHasAddToCompletedList();
            work.add(map("workflow_id", job.getId(), "owner_device_id", resourceNames.get(job.getMobileDevice()),
                "release_time", job.getReleaseTime(), "completion_time", complete ? job.getCompletionTime() : null,
                "flow_time", complete ? job.getFlowTime() : null));
            first = Math.min(first, job.getReleaseTime()); last = Math.max(last, job.getCompletionTime());
        }
        for (Task t : tasks) rows.add(taskRows.get(t));
        return map("status", status, "reason", reason, "final_clock_time", state.getClockTime(),
            "completed_workflow_count", state.getJobsCompleted().size(), "processed_event_count", processed,
            "makespan", status.equals("SUCCEEDED") ? last - first : null,
            "workflow_records", work, "task_records", rows, "events", events, "decisions", decisions);
    }

    Map<String,Object> loadedModel() {
        List<Object> resourceRows = new ArrayList<>(), workflowRows = new ArrayList<>();
        for (Object r : resources) resourceRows.add(map("id", resourceNames.get(r),
            "type", r instanceof MobileDevice ? "MOBILE" : ((Server) r).getType().toString(),
            "numeric_id", r instanceof MobileDevice ? ((MobileDevice) r).getId() : ((Server) r).getId(),
            "can_process_tasks", r instanceof MobileDevice ? ((MobileDevice) r).isCanProcessTask() : null));
        for (Job job : jobs) {
            List<Object> taskData = new ArrayList<>();
            for (Task t : job.getTaskList()) {
                List<Object> optionData = new ArrayList<>();
                for (TaskOption o : t.getTaskOptions()) optionData.add(map("resource_id", resourceNames.get(resource(o)),
                    "processing_time", o.getProcTime(), "upload_time", o.getUploadDelay(), "download_time", o.getDownloadDelay()));
                taskData.add(map("id", taskNames.get(t), "numeric_id", t.getId(),
                    "parents", t.getParentTaskList().stream().map(taskNames::get).toList(),
                    "children", t.getChildTaskList().stream().map(taskNames::get).toList(), "options", optionData));
            }
            workflowRows.add(map("id", job.getId(), "owner_device_id", resourceNames.get(job.getMobileDevice()),
                "release_time", job.getReleaseTime(), "tasks", taskData));
        }
        return map("resources", resourceRows, "workflows", workflowRows);
    }

    final class FixedDevice extends MobileDevice {
        FixedDevice(int id) { super(id, state, sequencing, routing); }
        @Override public void generateWorkflowJob() { suppressedGenerationCalls++; }
        @Override public void generateJob() { throw new IllegalStateException("LINKED/random generation is outside fixed DAG mode"); }
        @Override public void addEvent(AbstractEvent event) { super.addEvent(event); emitted(event, this); }
        @Override public boolean canAddToQueue(Process process) {
            // Call the original method once. Everything below is output-only;
            // no observed pending collection participates in scheduling.
            boolean allowed = super.canAddToQueue(process);
            if (detailed) {
                Object target = resource(process.getTaskOption());
                AbstractEvent root = simulation.getEventQueue().peek();
                List<Object> pending = new ArrayList<>();
                for (Process p : observedPending.get(target)) pending.add(taskKey(p.getTaskOption().getTask()));
                reservationChecks.add(map("event_sequence", processed, "time", state.getClockTime(),
                    "task", taskKey(process.getTaskOption().getTask()), "resource_id", resourceNames.get(target),
                    "available_time", available(target), "original_allowed", allowed,
                    "observed_pending_starts", pending, "global_root", root == null ? null : eventSnapshot(root)));
            }
            return allowed;
        }
        @Override public void completeJob(Job job) {
            // Explicit fixed-input statistics adaptation: every completed input is recorded.
            check(checkJobDone(job), "completeJob called for unfinished workflow");
            numJobsCompleted++;
            state.addCompletedJob(job);
            state.removeJobFromSystem(job);
        }
    }

    final class FixedSimulation extends DynamicSimulation {
        FixedSimulation() { super(state); }
        void runFixed() {
            status = "RUNNING";
            try {
                // Original mobiledeviceHaveEvent performs per-device poll -> global offer.
                while (mobiledeviceHaveEvent() || !eventQueue.isEmpty()) {
                    check(processed < maxEvents, "event limit exceeded");
                    AbstractEvent event = eventQueue.poll();
                    check(Double.isFinite(event.getTime()) && event.getTime() >= state.getClockTime(), "invalid/backward event time");
                    state.setClockTime(event.getTime()); processed++;
                    routeRounds.clear();
                    FixedDevice producer = producers.remove(event);
                    frame = eventSnapshot(event);
                    frame.put("sequence", processed); frame.put("staging_device", resourceNames.get(producer));
                    frame.put("before", detailed ? snapshot() : null);
                    frame.put("emitted", new ArrayList<>()); frame.put("actions", new ArrayList<>());
                    frame.put("error", null);
                    try {
                        if (event instanceof JobArrivalEvent) {
                            Job job = arrivals.get(event);
                            check(pendingArrivals.remove(job.getId()), "duplicate arrival");
                            state.getJobsInSystem().add(job); // supports t=0; no training release window
                        }
                        if (event instanceof TaskVisitEvent)
                            lifecycle(((TaskVisitEvent) event).getOperationOption(), "arrival", event.getTime());
                        if (event instanceof ProcessStartEvent) {
                            Process p = ((ProcessStartEvent) event).getProcess();
                            observedPending.get(resource(p.getTaskOption())).removeIf(x -> x == p);
                        }
                        event.trigger(event.getMobileDevice()); // ORIGINAL event implementations
                        if (event instanceof ProcessStartEvent) {
                            Process p = ((ProcessStartEvent) event).getProcess();
                            lifecycle(p.getTaskOption(), "start", event.getTime());
                            taskRows.get(p.getTaskOption().getTask()).put("compute_finish_time", p.getStartTime() + p.getTaskOption().getProcTime());
                        }
                        if (event instanceof ProcessFinishEvent)
                            lifecycle(((ProcessFinishEvent) event).getProcess().getTaskOption(), "finish", event.getTime());
                    } catch (RuntimeException ex) { frame.put("error", ex.toString()); throw ex; }
                    finally {
                        if (detailed) { frame.put("after", snapshot()); events.add(frame); }
                        frame = null;
                    }
                }
                check(state.getJobsCompleted().size() == jobs.size() && jobs.stream().allMatch(Job::isDone),
                      "events exhausted with unfinished workflows");
                status = "SUCCEEDED";
            } catch (RuntimeException ex) { status = "FAILED"; reason = ex.toString(); }
        }
    }

    final class ObservedRule extends AbstractRule {
        final FCFS fcfs;
        List<Object> currentScores;
        ObservedRule(RuleType type) { this.type = type; this.name = "observed-" + type; fcfs = new FCFS(type); }
        @Override public double priority(TaskOption option, Server server, SystemState systemState) {
            double score = type == RuleType.ROUTING && "fixed_resource".equals(config.get("routing_kind"))
                ? (resourceNames.get(resource(option)).equals(config.get("fixed_resource_id")) ? 0.0 : 1.0)
                : fcfs.priority(option, server, systemState);
            currentScores.add(map("option", optionKey(option), "priority", score));
            return score;
        }
        @Override public TaskOption nextTaskOption(RoutingDecisionSituation situation) {
            currentScores = new ArrayList<>();
            Task task = situation.getQueue().get(0).getTask();
            int round = routeRounds.merge(task, 1, Integer::sum);
            TaskOption selected = super.nextTaskOption(situation); // ORIGINAL selection and priorTo
            recordDecision(situation.getQueue(), selected, round);
            return selected;
        }
        @Override public TaskOption priorTask(SequencingDecisionSituation situation) {
            currentScores = new ArrayList<>();
            TaskOption selected = super.priorTask(situation);
            recordDecision(situation.getQueue(), selected, 1);
            return selected;
        }
        void recordDecision(List<TaskOption> candidates, TaskOption selected, int round) {
            decisionSequence++;
            if (!detailed) return;
            List<Object> candidateState = new ArrayList<>();
            for (TaskOption o : candidates) candidateState.add(map("option", optionKey(o), "ready_time", o.getReadyTime(),
                "dispatched", o.getTask().isDispatch(), "completed", o.getTask().isComplete(),
                "release_time", o.getTask().getJob().getReleaseTime(), "owner_numeric_id", o.getTask().getJob().getMobileDevice().getId()));
            Map<String,Object> record = map("event_sequence", processed, "decision_sequence", decisionSequence,
                "time", state.getClockTime(), "kind", type.toString(), "round", round,
                "candidates", currentScores, "selected", optionKey(selected),
                "candidate_state", candidateState, "resource_state", resourceSnapshot(true));
            decisions.add(record);
            list(frame.get("actions")).add(map("kind", "DECISION", "decision", record));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("usage: FixedInstanceMain request.json trace.json");
        Map<String,Object> request = obj(Json.parse(Files.readString(Path.of(args[0]), StandardCharsets.UTF_8)));
        FixedInstanceMain adapter = new FixedInstanceMain(request);
        Map<String,Object> loaded = adapter.loadedModel();
        adapter.simulation.runFixed();
        Map<String,Object> trace = map("schema_version", 1, "language", "java", "input", request.get("input"),
            "config", request.get("config"), "loaded_model", loaded, "result", adapter.result(),
            "observations", map("suppressed_generation_calls", adapter.suppressedGenerationCalls,
                "anomalies", adapter.anomalies, "pending_is_observed_only", true,
                "reservation_checks", adapter.reservationChecks,
                "random_generator_is_null", adapter.simulation.randomDataGenerator == null
                    && adapter.state.getMobileDevices().stream().allMatch(d -> d.randomDataGenerator == null)));
        Files.writeString(Path.of(args[1]), Json.write(trace) + "\n", StandardCharsets.UTF_8);
        if (!adapter.status.equals("SUCCEEDED")) System.exit(1);
    }
}
