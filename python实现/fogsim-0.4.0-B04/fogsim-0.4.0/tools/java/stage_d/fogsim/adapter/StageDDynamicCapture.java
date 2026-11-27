package fogsim.adapter;

import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import mengxu.algorithm.FCFS;
import mengxu.rule.RuleType;
import mengxu.simulation.*;
import mengxu.simulation.event.*;
import mengxu.simulation.state.SystemState;
import mengxu.taskscheduling.*;
import mengxu.taskscheduling.Process;
import mengxu.util.random.*;
import org.apache.commons.math3.random.RandomDataGenerator;

/** Read-only observations. Never calls a sampler, comparator or rule to observe it.
 * Baseline uses only delegating sampler/rule/heap audit wrappers, with original
 * source bytes. Minimal hashes complete observations; full also retains copies.
 */
public final class StageDDynamicCapture {
    static StageDDynamicCapture current;
    final StageDGP.Prepared prepared;
    final Map<Task,Integer> routeRounds = new IdentityHashMap<>();
    final List<Object> gpReads = new ArrayList<>();
    final String mode;
    final Map<String,Object> request;
    final Path directory;
    final List<Object> samples = new ArrayList<>(), events = new ArrayList<>(), decisions = new ArrayList<>();
    final List<Object> actions = new ArrayList<>();
    final List<Object> candidates = new ArrayList<>(), attempts = new ArrayList<>(), boundaries = new ArrayList<>();
    final List<Object> preBoundaries = new ArrayList<>(), eventErrors = new ArrayList<>();
    final List<String> preBoundaryHashes = new ArrayList<>();
    final Map<AbstractEvent,String> stagingDevices = new IdentityHashMap<>();
    final List<String> candidateHashes = new ArrayList<>(), attemptHashes = new ArrayList<>(), boundaryHashes = new ArrayList<>();
    final Map<Integer,Job> jobs = new LinkedHashMap<>();
    final Set<Integer> arrived = new LinkedHashSet<>();
    final Map<String,Integer> positions = new LinkedHashMap<>();
    Map<String,Object> pending;
    AbstractEvent activeEvent;
    RandomDataGenerator shared;
    double lastInterval;
    long eventSequence;

    StageDDynamicCapture(String mode, Map<String,Object> request, Path directory) {
        this.mode=mode; this.request=request; this.directory=directory;
        prepared=new StageDGP.Prepared(StageDGP.obj(request.get("routing_rule")),StageDGP.obj(request.get("sequencing_rule")));
    }
    static Map<String,Object> row(Object... values) {
        Map<String,Object> out=new LinkedHashMap<>();
        for(int i=0;i<values.length;i+=2) out.put((String)values[i],values[i+1]);
        return out;
    }
    static Object field(Object object, String name) {
        try {
            Class<?> cls=object.getClass();
            while(cls!=null) {
                try { Field f=cls.getDeclaredField(name); f.setAccessible(true); return f.get(object); }
                catch(NoSuchFieldException ex) { cls=cls.getSuperclass(); }
            }
            throw new NoSuchFieldException(name);
        } catch(ReflectiveOperationException ex) { throw new IllegalStateException(ex); }
    }
    static String hash(byte[] bytes) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
        catch(Exception ex) { throw new IllegalStateException(ex); }
    }
    static String digest(Object value) { return hash(Json.write(value).getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
    static void save(Path path, Object value) {
        try {
            Path temporary=path.resolveSibling(path.getFileName()+".tmp");
            Files.writeString(temporary,Json.write(value)+"\n");
            try { Files.move(temporary,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE); }
            catch(AtomicMoveNotSupportedException ex) { Files.move(temporary,path,StandardCopyOption.REPLACE_EXISTING); }
        } catch(IOException ex) { throw new UncheckedIOException(ex); }
    }
    static String resource(TaskOption option) {
        if(option.getServer()==null) return "M"+option.getMobileDevice().getId();
        return serverID(option.getServer(),option.getTask().getJob().getMobileDevice().getSystemState());
    }
    static String serverID(Server server, SystemState state) {
        int index=0;
        for(Server s:state.getServers()) {
            if(s==server) return (s.getType()==ServerType.EDGE?"E":"C")+index;
            if(s.getType()==server.getType()) index++;
        }
        throw new IllegalStateException("foreign server");
    }
    static Map<String,Object> environment(SystemState state) {
        List<Object> devices=new ArrayList<>(), servers=new ArrayList<>();
        for(MobileDevice d:state.getMobileDevices()) devices.add(row("id","M"+d.getId(),"numeric_id",d.getId(),
            "processing_rate",d.getProcessingRate(),"can_process_tasks",d.isCanProcessTask()));
        for(Server s:state.getServers()) servers.add(row("id",serverID(s,state),"numeric_id",s.getId(),
            "type",s.getType().toString(),"processing_rate",s.getProcessingRate(),
            "upload_bandwidth",s.getUploadBandwidth(),"download_bandwidth",s.getDownloadBandwidth()));
        return row("devices",devices,"servers",servers,"parameter_source","java-recorded",
                   "fingerprint",digest(row("devices",devices,"servers",servers)));
    }
    @SuppressWarnings("unchecked")
    Map<String,Object> template(int type) {
        for(Object item:(List<?>)request.get("templates")) {
            Map<String,Object> t=(Map<String,Object>)item;
            if(((Number)t.get("dag_type_id")).intValue()==type) return t;
        }
        throw new IllegalStateException("template metadata missing: "+type);
    }
    @SuppressWarnings("unchecked")
    static String xmlID(Map<String,Object> template, int index) {
        return (String)((Map<String,Object>)((List<?>)template.get("tasks")).get(index)).get("xml_id");
    }
    public static void beforeClear(MobileDevice device, int type, String path,
                                   double release, double weight, List<Task> taskList) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        if(c.pending!=null) throw new IllegalStateException("unclosed candidate");
        Map<String,Object> template=c.template(type);
        List<Object> tasks=new ArrayList<>(), edges=new ArrayList<>();
        for(Task t:taskList) {
            String id=xmlID(template,t.getId());
            List<Object> options=new ArrayList<>();
            for(TaskOption o:t.getTaskOptions()) options.add(row("resource_id",o.getServer()==null?"M"+device.getId():serverID(o.getServer(),device.getSystemState()),
                "processing_time",o.getProcTime(),"upload_time",o.getUploadDelay(),"download_time",o.getDownloadDelay()));
            tasks.add(row("id",id,"workload",t.getWorkload(),"data_size",t.getData(),
                "total_input_data",t.getAllInputDataTotal(),"total_output_data",t.getAllOutputDataTotal(),"options",options));
            for(Task child:t.getChildTaskList()) edges.add(row("parent_id",id,"child_id",xmlID(template,child.getId()),
                "data_size",t.getChildOutputData(child.getId())));
        }
        Map<String,Object> input=row("candidate_id",device.getSystemState().getAllNumJobsReleased(),
            "owner_device_id","M"+device.getId(),"template_ref",row("dag_type_id",type,"source_sha256",template.get("source_sha256")),
            "release_time",release,"inter_release_time",c.lastInterval,"weight",weight,"tasks",tasks,"edges",edges);
        c.pending=row("record_id",Integer.toString(c.candidateHashes.size()+1),"workflow_input",input);
        c.candidateHashes.add(digest(c.pending));
    }
    public static void afterAdmission(MobileDevice device, Job job, boolean accepted) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        if(c.pending==null) throw new IllegalStateException("missing pre-clear candidate");
        Object cause=null;
        if(c.activeEvent!=null) {
            if(!(c.activeEvent instanceof JobArrivalEvent)) throw new IllegalStateException("generation outside Arrival");
            cause=((Job)field(c.activeEvent,"job")).getId();
        }
        Map<String,Object> attempt=row("attempt_sequence",c.attemptHashes.size()+1,
            "phase",cause==null?"initialize":"after_arrival","owner_device_id","M"+device.getId(),
            "generation_clock_time",device.getSystemState().getClockTime(),"causing_workflow_id",cause,
            "event_sequence",cause==null?null:c.eventSequence,"candidate_ref",c.pending.get("record_id"),
            "observed_acceptance",accepted,"rejection_reason",accepted?null:"REJECTED_RELEASE_NOT_FUTURE");
        c.attemptHashes.add(digest(attempt));
        if(accepted) c.jobs.put(job.getId(),job);
        if(c.mode.equals("full")) {
            c.candidates.add(c.pending); c.attempts.add(attempt);
            c.saveInput(device.getSystemState(),false,"RUN_IN_PROGRESS");
        }
        c.pending=null;
    }
    public static void beforeEvent(DynamicSimulation sim) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        c.routeRounds.clear();
        Map<String,Object> boundary=row("event_sequence",c.eventSequence,"state",c.state(sim.getSystemState()));
        c.preBoundaryHashes.add(digest(boundary));
        if(c.mode.equals("full")) c.preBoundaries.add(boundary);
    }
    public static void afterEvent(DynamicSimulation sim) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        Map<String,Object> boundary=row("event_sequence",c.eventSequence,"state",c.state(sim.getSystemState()));
        c.boundaryHashes.add(digest(boundary));
        if(c.mode.equals("full")) {
            c.boundaries.add(boundary);
            c.eventErrors.add(row("event_sequence",c.eventSequence,"error",null));
        }
    }
    Map<String,Object> event(AbstractEvent e) {
        Job job; TaskOption option=null; Process process=null;
        if(e instanceof JobArrivalEvent) job=(Job)field(e,"job");
        else {
            if(e instanceof TaskVisitEvent) option=(TaskOption)field(e,"taskOption");
            else { process=(Process)field(e,"process"); option=process.getTaskOption(); }
            job=option.getTask().getJob();
        }
        jobs.putIfAbsent(job.getId(),job);
        Map<String,Object> out=row("kind",e.getClass().getSimpleName(),"time",e.getTime(),"producer_device_id","M"+e.getMobileDevice().getId(),
            "workflow_id",job.getId(),"task_java_index",option==null?null:option.getTask().getId(),
            "resource_id",option==null?null:resource(option),"start_time",process==null?null:process.getStartTime(),
            "finish_time",process==null?null:process.getFinishTime());
        if(mode.equals("full")||mode.equals("minimal")) {
            String staging=stagingDevices.get(e);
            if(staging==null) throw new IllegalStateException("missing actual staging observation");
            out.put("owner_device_id","M"+e.getMobileDevice().getId());
            out.put("staging_device_id",staging);
        }
        return out;
    }
    static Map<String,Object> option(TaskOption o) {
        return row("workflow_id",o.getTask().getJob().getId(),"task_java_index",o.getTask().getId(),
            "resource_id",resource(o),"ready_time",o.getReadyTime(),"priority",StageDGP.tag(o.getPriority()));
    }
    void decision(String kind,List<TaskOption> queue,TaskOption selected,SystemState state) {
        List<Object> options=new ArrayList<>();
        for(TaskOption o:queue) options.add(option(o));
        Map<String,Object> record=row("event_sequence",eventSequence,"clock_time",state.getClockTime(),
            "kind",kind,"options",options,"selected",option(selected));
        record.put("round",kind.equals("routing")?routeRounds.get(queue.get(0).getTask()):1);
        record.put("rule_id",StageDGP.obj(StageDGP.obj(prepared.manifest.get("bindings")).get(kind)).get("rule_id"));
        decisions.add(record);
        if(mode.equals("full")||mode.equals("minimal")) actions.add(row("event_sequence",eventSequence,"kind","DECISION","decision",record));
    }
    public static void afterStage(MobileDevice device, AbstractEvent event) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        c.stagingDevices.put(event,"M"+device.getId());
        c.actions.add(row("event_sequence",c.activeEvent==null?null:c.eventSequence,"kind","EMIT","event",c.event(event)));
    }
    public static void afterGeneratedArrival(MobileDevice device, Job job) {
        StageDDynamicCapture c=current;
        if(c==null) return;
        AbstractEvent generated=null;
        for(AbstractEvent e:device.eventQueue) {
            if(e instanceof JobArrivalEvent && field(e,"job")==job) { generated=e; break; }
        }
        if(generated==null) throw new IllegalStateException("generated Arrival missing from staging queue");
        c.stagingDevices.put(generated,"M"+device.getId());
        c.actions.add(row("event_sequence",c.activeEvent==null?null:c.eventSequence,"kind","EMIT","event",c.event(generated)));
    }
    static List<Integer> ids(List<Job> values) {
        List<Integer> out=new ArrayList<>(); for(Job j:values) out.add(j.getId()); return out;
    }
    Map<String,Object> state(SystemState state) {
        List<Object> resources=new ArrayList<>(), all=new ArrayList<>();
        for(MobileDevice d:state.getMobileDevices()) {
            List<Object> queue=new ArrayList<>(); for(TaskOption o:d.getQueue()) queue.add(option(o));
            resources.add(row("id","M"+d.getId(),"available_time",d.getReadyTime(),"queue",queue,
                "total_processing",d.totalProcTimeInQueue(),"total_occupancy",d.totalProcTimeAndUpLoadAndDownLoadTimeInQueue(),
                "tasks_completed",d.getNumTasksCompleted(),"staged_events",d.eventQueue.size()));
        }
        for(Server s:state.getServers()) {
            List<Object> queue=new ArrayList<>(); for(TaskOption o:s.getQueue()) queue.add(option(o));
            resources.add(row("id",serverID(s,state),"available_time",s.getReadyTime(),"queue",queue,
                "total_processing",s.totalProcTimeInQueue(),"total_occupancy",s.totalProcTimeAndUpLoadAndDownLoadTimeInQueue(),
                "tasks_completed",s.getNumTasksCompleted()));
        }
        for(Job j:jobs.values()) {
            List<Object> tasks=new ArrayList<>();
            for(Task t:j.getTaskList()) {
                List<Object> options=new ArrayList<>(); for(TaskOption o:t.getTaskOptions()) options.add(option(o));
                tasks.add(row("java_index",t.getId(),"dispatched",t.isDispatch(),"completed",t.isComplete(),"options",options,
                    "edge_maps_cleared",((Map<?,?>)field(t,"inputDateMap")).isEmpty() && ((Map<?,?>)field(t,"outputDateMap")).isEmpty()));
            }
            all.add(row("id",j.getId(),"completion_time",j.getCompletionTime(),"tasks",tasks));
        }
        return row("clock_time",state.getClockTime(),"G",state.getAllNumJobsReleased(),
            "B",state.getFirstArriveJobRecordedTime(),"statistical_workflow_ids",ids(state.getJobsCompleted()),
            "active_workflow_ids",ids(state.getJobsInSystem()),"resources",resources,"workflows",all);
    }
    static Map<String,Object> nativeNumber(double value) {
        return row("kind",Double.isInfinite(value)?(value>0?"POSITIVE_INFINITY":"NEGATIVE_INFINITY"):
                   Double.isNaN(value)?"NAN":value==Double.MAX_VALUE?"DOUBLE_MAX_VALUE":"FINITE",
                   "value",Double.isFinite(value)?value:null,"java_text",Double.toString(value));
    }
    Map<String,Object> nativeResult(DynamicSimulation sim) {
        SystemState state=sim.getSystemState();
        List<Integer> completed=new ArrayList<>(), notArrived=new ArrayList<>(), unfinished=new ArrayList<>();
        for(Job j:jobs.values()) {
            if(j.isDone()) completed.add(j.getId()); else unfinished.add(j.getId());
            if(!arrived.contains(j.getId())) notArrived.add(j.getId());
        }
        return row("target_reached",sim.getCurrentCompletedJobsNum()>=((Number)request.get("N")).intValue(),
            "clock_time",state.getClockTime(),"G",state.getAllNumJobsReleased(),"B",state.getFirstArriveJobRecordedTime(),
            "R",sim.getCurrentCompletedJobsNum(),"completed_workflow_ids",completed,
            "statistical_workflow_ids",ids(state.getJobsCompleted()),"not_arrived_workflow_ids",notArrived,
            "unfinished_workflow_ids",unfinished,"pending_global_events",sim.getEventQueue().size(),
            "makespan",nativeNumber(sim.makespan()),"mean_flowtime",nativeNumber(sim.meanFlowtime()));
    }
    String rngState(RandomDataGenerator rng) {
        try {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            new ObjectOutputStream(bytes).writeObject(rng.getRandomGenerator());
            return hash(bytes.toByteArray());
        } catch(IOException ex) { throw new UncheckedIOException(ex); }
    }
    void saveInput(SystemState state,boolean complete,String termination) {
        Map<String,Object> input=row("format","fogsim.dynamic-replay","schema_version",2,
            "origin",request.get("origin"),"initial_state",request.get("initial_state"),
            "effective_config",request.get("effective_config"),"units",row("time","s","workload","model_workload","data","model_data"),
            "environment",environment(state),"templates",request.get("templates"),"candidates",candidates,
            "generation_attempts",attempts,"capture",row("complete",complete,"complete_attempt_count",attempts.size(),
            "write_interrupted",false,"process_interrupted",!complete,"termination",termination));
        input.put("rule_manifest",prepared.manifest);input.put("score_encoding_version","ieee754-binary64-hex-v1");
        save(directory.resolve("input.json"),input);
    }
    void finish(DynamicSimulation sim,boolean complete,String termination) {
        Map<String,Object> result=nativeResult(sim);
        // Baseline knows all accepted jobs via actual arrivals and final pending queues.
        // Pending initialization arrivals may not have been polled at early stop.
        for(AbstractEvent e:sim.getEventQueue()) if(e instanceof JobArrivalEvent) {
            Job j=(Job)field(e,"job"); jobs.putIfAbsent(j.getId(),j);
        }
        for(MobileDevice d:sim.getSystemState().getMobileDevices())
            for(AbstractEvent e:d.eventQueue) if(e instanceof JobArrivalEvent) {
                Job j=(Job)field(e,"job"); jobs.putIfAbsent(j.getId(),j);
            }
        // Normalize workflow observation order to accepted ID for baseline/full agreement.
        List<Integer> keys=new ArrayList<>(jobs.keySet()); Collections.sort(keys);
        Map<Integer,Job> sorted=new LinkedHashMap<>(); for(int key:keys) sorted.put(key,jobs.get(key));
        jobs.clear(); jobs.putAll(sorted); result=nativeResult(sim);
        Map<String,Object> audit=row("samples",samples,"events",events,"decisions",decisions,
            "rng_final_state_sha256",rngState(sim.getRandomDataGenerator()),"native_result",result,
            "final_state",state(sim.getSystemState()),"environment",environment(sim.getSystemState()));
        save(directory.resolve("audit.json"),audit);
        save(directory.resolve("observation.json"),row("mode",mode,"candidate_sha256",candidateHashes,
            "attempt_sha256",attemptHashes,"post_trigger_sha256",boundaryHashes,"pre_trigger_sha256",preBoundaryHashes,"interleaved_actions_sha256",mode.equals("baseline")||mode.equals("plain")?null:digest(actions)));
        if(mode.equals("full")) {
            Map<String,Object> payload=row("events",events,"decisions",decisions,"actions",actions,
                "post_trigger_states",boundaries,"pre_trigger_states",preBoundaries,"event_errors",eventErrors,
                "native",result,"final_state",state(sim.getSystemState()),"feature_observations",gpReads);
            save(directory.resolve("reference.json"),StageDProtocol.envelope("dynamic",prepared.manifest,payload,
                row("events",events.size(),"decisions",decisions.size(),"attempts",attempts.size(),"capture_complete",complete,"target_reached",result.get("target_reached"))));
            saveInput(sim.getSystemState(),complete,termination);
        }
    }
    double sample(String role,AbstractRealSampler delegate,RandomDataGenerator rng) {
        checkRng(rng); double value=delegate.next(rng);
        Map<?,?> scripted=(Map<?,?>)request.get("scripted_values");
        if(scripted!=null && scripted.containsKey(role)) {
            List<?> values=(List<?>)scripted.get(role); int at=positions.getOrDefault(role,0);
            if(at>=values.size()) throw new IllegalStateException("script exhausted: "+role);
            value=((Number)values.get(at)).doubleValue(); positions.put(role,at+1);
        }
        // Script boundary fixtures still consume the original draw, then substitute
        // a frozen business input. These fixtures are explicitly tagged in origin.
        samples.add(row("role",role,"value",value));
        if(role.equals("inter_release_time")) lastInterval=value;
        return value;
    }
    void checkRng(RandomDataGenerator rng) {
        if(shared==null) shared=rng;
        if(shared!=rng) throw new IllegalStateException("input RNG not shared");
    }
    static final class Real extends AbstractRealSampler {
        final String role; final AbstractRealSampler delegate;
        Real(String role,AbstractRealSampler delegate) {this.role=role; this.delegate=delegate;}
        public double next(RandomDataGenerator rng) {return current.sample(role,delegate,rng);}
        public void setLower(double v) {delegate.setLower(v);} public void setUpper(double v) {delegate.setUpper(v);}
        public void setMean(double v) {delegate.setMean(v);} public double getMean() {return delegate.getMean();}
        public AbstractRealSampler clone() {return new Real(role,delegate.clone());}
    }
    static final class IntegerSampler extends AbstractIntegerSampler {
        final AbstractIntegerSampler delegate;
        IntegerSampler(AbstractIntegerSampler delegate) {this.delegate=delegate;}
        public int next(RandomDataGenerator rng) {
            current.checkRng(rng); int value=delegate.next(rng);
            current.samples.add(row("role","workflow_type","value",value)); return value;
        }
        public void setLower(int v) {delegate.setLower(v);} public void setUpper(int v) {delegate.setUpper(v);}
        public void setMean(double v) {delegate.setMean(v);} public double getMean() {return delegate.getMean();}
        public AbstractIntegerSampler clone() {return new IntegerSampler(delegate.clone());}
    }
    static final class AuditRule extends mengxu.rule.AbstractRule {
        final String role; final mengxu.rule.AbstractRule delegate;
        AuditRule(RuleType t){type=t;role=t==RuleType.ROUTING?"routing":"sequencing";delegate=current.prepared.rules.get(role);}
        public double priority(TaskOption o,Server server,SystemState state){
            current.prepared.begin(role);double value;
            try{value=delegate.priority(o,server,state);}finally{current.gpReads.add(row("event_sequence",current.eventSequence,"time",state.getClockTime(),"role",role,
                "option",java.util.List.of(o.getTask().getJob().getId(),o.getTask().getId(),resource(o)),"reads",current.prepared.end()));}
            return value;
        }
        public TaskOption nextTaskOption(RoutingDecisionSituation situation){current.routeRounds.merge(situation.getQueue().get(0).getTask(),1,Integer::sum);TaskOption chosen=super.nextTaskOption(situation);current.decision("routing",situation.getQueue(),chosen,situation.getSystemState());return chosen;}
        public TaskOption priorTask(SequencingDecisionSituation situation){TaskOption chosen=super.priorTask(situation);current.decision("sequencing",situation.getQueue(),chosen,situation.getSystemState());return chosen;}
    }
    static final class AuditQueue extends PriorityQueue<AbstractEvent> {
        public AbstractEvent poll() {
            AbstractEvent e=super.poll();
            if(e!=null) {
                current.activeEvent=e; current.eventSequence++;
                Map<String,Object> record=current.event(e); record.put("event_sequence",current.eventSequence);
                current.events.add(record);
                if(e instanceof JobArrivalEvent) current.arrived.add(((Job)field(e,"job")).getId());
            }
            return e;
        }
    }
}
