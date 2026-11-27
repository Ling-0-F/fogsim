package fogsim.adapter;

import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import mengxu.algorithm.FCFS;
import mengxu.rule.RuleType;
import mengxu.simulation.*;
import mengxu.simulation.state.SystemState;
import mengxu.simulation.event.AbstractEvent;
import mengxu.taskscheduling.*;
import mengxu.util.random.*;
import org.apache.commons.math3.random.RandomDataGenerator;

/** Original lifecycle, completion/admission and run-guard component probes.
 * No source overlay. All injected states below are explicitly component probes,
 * not claimed to be naturally reachable full scheduling experiments.
 */
public final class Step5Probe {
    static Map<String,Object> row(Object... v) {
        Map<String,Object> out=new LinkedHashMap<>();for(int i=0;i<v.length;i+=2)out.put((String)v[i],v[i+1]);return out;
    }
    static void set(Object obj,String name,Object value) {
        try {Field f=obj.getClass().getDeclaredField(name);f.setAccessible(true);f.set(obj,value);}
        catch(Exception ex){throw new IllegalStateException(ex);}
    }
    static Object get(Object obj,String name) {
        try {Field f=obj.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(obj);}
        catch(Exception ex){throw new IllegalStateException(ex);}
    }
    static String rngHash(RandomDataGenerator rng) {
        try {
            ByteArrayOutputStream b=new ByteArrayOutputStream();new ObjectOutputStream(b).writeObject(rng.getRandomGenerator());
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b.toByteArray()));
        }catch(Exception ex){throw new IllegalStateException(ex);}
    }
    static final List<Object> calls=new ArrayList<>();
    static final class Real extends AbstractRealSampler {
        final String role;final AbstractRealSampler delegate;final boolean zero;
        Real(String role,AbstractRealSampler delegate,boolean zero){this.role=role;this.delegate=delegate;this.zero=zero;}
        public double next(RandomDataGenerator rng){
            calls.add(row("role",role,"rng_before",rngHash(rng)));
            double value=delegate.next(rng);return zero&&role.equals("delta")?0:value;
        }
        public void setLower(double v){delegate.setLower(v);}public void setUpper(double v){delegate.setUpper(v);}
        public void setMean(double v){delegate.setMean(v);}public double getMean(){return delegate.getMean();}
        public AbstractRealSampler clone(){return new Real(role,delegate.clone(),zero);}
    }
    static final class TypeSampler extends AbstractIntegerSampler {
        final UniformIntegerSampler delegate=new UniformIntegerSampler(0,0);
        public int next(RandomDataGenerator rng){calls.add(row("role","type","rng_before",rngHash(rng)));return delegate.next(rng);}
        public void setLower(int v){}public void setUpper(int v){}public void setMean(double v){}
        public double getMean(){return 0;}public AbstractIntegerSampler clone(){return new TypeSampler();}
    }
    static AbstractRealSampler real(String role,AbstractRealSampler s,boolean zero){return new Real(role,s,zero);}
    static DynamicSimulation sim(long seed,int N,int W,boolean zero){
        return new DynamicSimulation(seed,new FCFS(RuleType.SEQUENCING),new FCFS(RuleType.ROUTING),N,W,2,1,1,
            real("workload",new UniformSampler(1,2),zero),real("data",new UniformSampler(0,1),zero),
            real("edge",new UniformSampler(0,1),zero),real("delta",new ExponentialSampler(),zero),
            real("weight",new TwoSixTwoSampler(),zero),real("upload_cloud",new BandwidthCloudSampler(),zero),
            real("download_cloud",new BandwidthCloudSampler(),zero),real("upload_edge",new BandwidthEdgeSampler(),zero),
            real("download_edge",new BandwidthEdgeSampler(),zero),real("rate_cloud",new UniformSampler(30,40),zero),
            real("rate_edge",new UniformSampler(20,30),zero),real("rate_device",new UniformSampler(10,20),zero),new TypeSampler(),true);
    }
    static List<Object> environment(DynamicSimulation sim){
        List<Object> out=new ArrayList<>();
        for(MobileDevice d:sim.getSystemState().getMobileDevices())out.add(row("id","M"+d.getId(),"rate",d.getProcessingRate()));
        for(Server s:sim.getSystemState().getServers())out.add(row("id","S"+s.getId(),"rate",s.getProcessingRate(),"up",s.getUploadBandwidth(),"down",s.getDownloadBandwidth()));
        return out;
    }
    static String seedOrigin(long seed){RandomDataGenerator r=new RandomDataGenerator();r.reSeed(seed);return rngHash(r);}
    static List<Object> lifecycle(long seed){
        calls.clear();DynamicSimulation sim=sim(seed,1,0,false);
        // Deliberate B continuation probe: N+W=1 prevents setup from overwriting B.
        set(sim.getSystemState(),"firstArriveJobRecordedTime",1000000.0);
        List<Object> env=environment(sim);List<Object> result=new ArrayList<>();
        for(String operation:List.of("run","reset","run","reset_explicit","run","rerun","rotateSeed")){
            String before=rngHash(sim.getRandomDataGenerator());calls.clear();
            double beforeB=sim.getSystemState().getFirstArriveJobRecordedTime();
            long effectiveSeed=(Long)get(sim,"seed");
            if(operation.equals("run"))sim.run();
            else if(operation.equals("reset"))sim.reset();
            else if(operation.equals("reset_explicit"))sim.reset(seed);
            else if(operation.equals("rerun"))sim.rerun();
            else {sim.rotateSeed();effectiveSeed+=10000;}
            boolean shared=true;
            for(MobileDevice d:sim.getSystemState().getMobileDevices())shared &= get(d,"randomDataGenerator")==sim.getRandomDataGenerator();
            List<Object> sampleCalls=new ArrayList<>(calls);
            boolean reset=operation.startsWith("reset")||operation.equals("rotateSeed");
            boolean consumed=!sampleCalls.isEmpty();
            String first=consumed?(String)((Map<?,?>)sampleCalls.get(0)).get("rng_before"):null;
            boolean passed=environment(sim).equals(env)&&shared&&beforeB==sim.getSystemState().getFirstArriveJobRecordedTime();
            if(reset)passed &= consumed&&first.equals(seedOrigin(effectiveSeed))&&sim.getCurrentCompletedJobsNum()==0;
            if(operation.equals("rerun"))passed &= consumed&&first.equals(before)&&sim.getCurrentCompletedJobsNum()>=1;
            for(Object x:sampleCalls){String role=(String)((Map<?,?>)x).get("role");passed &= !role.startsWith("rate_")&&!role.startsWith("upload_")&&!role.startsWith("download_");}
            passed &= (Long)get(sim,"seed")==effectiveSeed;
            result.add(row("operation",operation,"public_seed",effectiveSeed,"B_before",beforeB,"B_after",sim.getSystemState().getFirstArriveJobRecordedTime(),
                "rng_before",before,"rng_after",rngHash(sim.getRandomDataGenerator()),"samples",sampleCalls,"passed",passed,
                "R",sim.getCurrentCompletedJobsNum(),"environment",env,"shared_rng",shared));
        }
        return result;
    }
    static List<Object> completion(){
        List<Object> out=new ArrayList<>();
        for(int[] v:new int[][]{{2,2,0,1,10,0},{3,2,0,1,10,1},{3,2,-1,1,10,0},{3,2,10,10,10,1},{3,2,1,11,10,0}}){
            DynamicSimulation sim=sim(7,3,v[1],true);SystemState state=sim.getSystemState();
            set(state,"allNumJobsReleased",v[0]);set(state,"firstArriveJobRecordedTime",(double)v[4]);
            MobileDevice d=state.getMobileDevices().get(0);
            Job job=new Job(v[2],v[3],1,d,new ArrayList<>(),JobType.DAG);state.getJobsInSystem().add(job);
            d.completeJob(job);
            int before=state.getJobsCompleted().size();set(state,"firstArriveJobRecordedTime",100.0);
            int after=state.getJobsCompleted().size();
            out.add(row("G",v[0],"W",v[1],"id",v[2],"release",v[3],"B",v[4],"recorded",before,
                "no_retroactive_record",before==after,"passed",before==v[5]&&before==after&&((Number)get(d,"numJobsCompleted")).intValue()==1));
        }
        return out;
    }
    static List<Object> admission(){
        DynamicSimulation sim=sim(7,2,2,true);SystemState state=sim.getSystemState();List<Object> out=new ArrayList<>();
        double[] releases={20,10,30,5,1,0};double[] cutoffs={20,10,30,30,30,30};
        for(int i=0;i<releases.length;i++){
            int G=state.getAllNumJobsReleased();Job j=new Job(G,releases[i],1,state.getMobileDevices().get(0),new ArrayList<>(),JobType.DAG);
            boolean accepted=state.addJobToSystem(j);
            out.add(row("G_before",G,"release",releases[i],"accepted",accepted,"G_after",state.getAllNumJobsReleased(),
                "B",state.getFirstArriveJobRecordedTime(),"passed",accepted==(i<5)&&state.getFirstArriveJobRecordedTime()==cutoffs[i]&&state.getAllNumJobsReleased()==(i<5?i+1:5)));
        }
        return out;
    }
    static final class GuardEvent extends AbstractEvent{
        final DynamicSimulation sim;final String kind;final int value;
        GuardEvent(DynamicSimulation sim,String kind,int value){super(1,sim.getSystemState().getMobileDevices().get(0));this.sim=sim;this.kind=kind;this.value=value;}
        public void trigger(MobileDevice d){
            if(kind.equals("count"))set(sim,"count",value-1); // original increment will produce value
            if(kind.equals("device"))for(int i=0;i<value;i++)d.getQueue().add(null);
            if(kind.equals("server")||kind.equals("target_server"))for(int i=0;i<value;i++)sim.getSystemState().getServers().get(0).getQueue().add(null);
            if(kind.equals("generated"))set(sim.getSystemState(),"allNumJobsReleased",value);
            if(kind.equals("target_server"))set(d,"throughput",2);
        }
        public void addSequencingDecisionSituation(MobileDevice d,List<SequencingDecisionSituation>x,int n){trigger(d);}
        public void addRoutingDecisionSituation(MobileDevice d,List<RoutingDecisionSituation>x,int n){trigger(d);}
    }
    static List<Object> guards(){
        List<Object> out=new ArrayList<>();
        for(String kind:List.of("count","device","server","generated","target_server")){
            int limit=kind.equals("count")?400000:kind.equals("generated")?1000:400;
            for(int extra=0;extra<=1;extra++){
                DynamicSimulation sim=sim(7,2,0,true);set(sim.getSystemState().getMobileDevices().get(0),"throughput",1);
                sim.getEventQueue().add(new GuardEvent(sim,kind,limit+extra));sim.run();
                boolean hit=sim.getSystemState().getClockTime()==Double.MAX_VALUE;
                out.add(row("kind",kind,"actual",limit+extra,"hit",hit,"clock_time",sim.getSystemState().getClockTime(),
                    "R",sim.getCurrentCompletedJobsNum(),"passed",hit==(extra==1)));
            }
        }
        return out;
    }
    static Map<String,Object> ownerProducer(){
        DynamicSimulation sim=sim(7,2,0,true);SystemState state=sim.getSystemState();
        MobileDevice producer=state.getMobileDevices().get(0),owner=state.getMobileDevices().get(1);
        Server server=state.getServers().get(0);server.setReadyTime(1);
        Task first=new Task(0,1,0),queued=new Task(0,1,0);
        Job a=new Job(0,0,1,producer,new ArrayList<>(List.of(first)),JobType.DAG);
        Job b=new Job(1,0,1,owner,new ArrayList<>(List.of(queued)),JobType.DAG);
        first.setJob(a);queued.setJob(b);first.setDispatch(true);queued.setDispatch(true);
        TaskOption o0=new TaskOption(first,server,1,0,0),o1=new TaskOption(queued,server,1,0,0);
        first.addTaskOption(o0);queued.addTaskOption(o1);server.addToQueue(o1);
        state.getJobsInSystem().add(a);state.getJobsInSystem().add(b);
        set(state,"allNumJobsReleased",2);set(state,"firstArriveJobRecordedTime",100.0);state.setClockTime(1);
        mengxu.taskscheduling.Process running=new mengxu.taskscheduling.Process(server,o0,0);
        new mengxu.simulation.event.ProcessFinishEvent(1,running,producer).trigger(producer);
        AbstractEvent next=producer.eventQueue.peek();
        boolean passed=next instanceof mengxu.simulation.event.ProcessStartEvent&&next.getMobileDevice()==owner&&owner.eventQueue.isEmpty();
        return row("scope","manual valid server-queue continuation component probe","staging_device_id","M0",
            "event_owner_device_id",next==null?null:"M"+next.getMobileDevice().getId(),"passed",passed);
    }
    public static void main(String[] args)throws Exception{
        List<Object> life=new ArrayList<>();
        for(long seed:new long[]{0,-1,Long.MIN_VALUE,Long.MAX_VALUE})life.add(row("initial_seed",seed,"operations",lifecycle(seed)));
        Map<String,Object> result=row("scope","original Java lifecycle and manually injected component probes; no Python RNG value parity",
            "lifecycle",life,"completion",completion(),"admission",admission(),"guards",guards(),"owner_producer",ownerProducer());
        Files.writeString(Path.of(args[0]),Json.write(result)+"\n");
    }
}
