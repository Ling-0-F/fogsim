package fogsim.adapter;

import java.nio.file.*;
import java.util.*;
import mengxu.simulation.DynamicSimulation;
import mengxu.simulation.state.SystemState;
import mengxu.taskscheduling.*;

/** Observation only: no RNG calls, no reset, no model writes in mark(). */
public final class S9LifeObserver {
    static final List<Object> rows = new ArrayList<>();
    static String operation = "construct";
    public static void mark(String boundary, DynamicSimulation sim) {
        SystemState state = sim.getSystemState();
        List<Object> queues = new ArrayList<>();
        for (MobileDevice d : state.getMobileDevices())
            queues.add(Step5Probe.row("device",d.getId(),"queue",d.getQueue().size(),
                "events",d.eventQueue.size(),"throughput",d.getThroughput()));
        for (Server s : state.getServers())
            queues.add(Step5Probe.row("server",s.getId(),"queue",s.numTaskInQueue()));
        rows.add(Step5Probe.row("operation",operation,"boundary",boundary,
            "seed",Step5Probe.get(sim,"seed"),"environment",Step5Probe.environment(sim),
            "B",state.getFirstArriveJobRecordedTime(),"clock",state.getClockTime(),
            "generated",state.getAllNumJobsReleased(),"recorded",sim.getCurrentCompletedJobsNum(),
            "jobs_in_system",state.getJobsInSystem().size(),"jobs_completed",state.getJobsCompleted().size(),
            "event_queue",sim.getEventQueue().size(),"queues",queues,
            "rng",Step5Probe.rngHash(sim.getRandomDataGenerator()),"samples_so_far",Step5Probe.calls.size()));
    }
    static Object sequence(long seed,int N,int W,boolean sentinel) {
        rows.clear(); Step5Probe.calls.clear(); operation="construct";
        String origin=Step5Probe.seedOrigin(seed);
        DynamicSimulation sim=Step5Probe.sim(seed,N,W,false);
        mark("after_operation",sim);
        if (sentinel) Step5Probe.set(sim.getSystemState(),"firstArriveJobRecordedTime",1000000.0);
        for (String op:List.of("run","rerun","reset","run_after_reset","rotateSeed","run_after_rotate")) {
            operation=op; mark("before_operation",sim);
            if(op.equals("rerun"))sim.rerun();
            else if(op.equals("reset"))sim.reset();
            else if(op.equals("rotateSeed"))sim.rotateSeed();
            else sim.run();
            mark("after_operation",sim);
        }
        return Step5Probe.row("initial_seed",seed,"N",N,"W",W,"sentinel_B_probe",sentinel,
            "seed_origin_rng",origin,"rotated_seed_origin_rng",Step5Probe.seedOrigin(seed+10000),
            "rows",new ArrayList<>(rows),"samples",new ArrayList<>(Step5Probe.calls));
    }
    public static void main(String[] args)throws Exception {
        Object result=Step5Probe.row("format","fogsim.s9-java-lifecycle","schema_version",1,
            "cases",List.of(sequence(7,2,1,false),sequence(7,1,0,true),sequence(Long.MAX_VALUE,1,0,true)));
        Files.writeString(Path.of(args[0]),Json.write(result)+"\n");
    }
}
