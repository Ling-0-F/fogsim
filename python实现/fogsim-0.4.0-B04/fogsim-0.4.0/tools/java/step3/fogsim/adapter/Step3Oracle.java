package fogsim.adapter;

import java.nio.file.*;
import java.lang.reflect.Field;
import java.util.*;
import org.apache.commons.math3.random.RandomDataGenerator;
import org.jdom2.Element;
import org.jdom2.input.SAXBuilder;
import mengxu.simulation.DynamicSimulation;
import mengxu.simulation.state.SystemState;
import mengxu.taskscheduling.*;
import mengxu.util.random.*;

/** Scoped generation oracle. Original constructors/setup/generate methods run
 * unchanged. Scripted samplers supply identical business inputs to both sides.
 * This is not a full input exporter, replay format, or scheduling experiment.
 */
public final class Step3Oracle {
    static Map<String,Object> row(Object... values) {
        Map<String,Object> out = new LinkedHashMap<>();
        for (int i=0; i<values.length; i+=2) out.put((String)values[i], values[i+1]);
        return out;
    }
    static final class Feed {
        final Map<String,Object> values;
        final Map<String,Integer> positions = new LinkedHashMap<>();
        final List<Object> calls = new ArrayList<>();
        RandomDataGenerator shared;
        Feed(Map<String,Object> values) { this.values=values; }
        double next(String role, RandomDataGenerator rng) {
            if (shared==null) shared=rng;
            if (shared!=rng) throw new IllegalStateException("input RNG not shared");
            List<?> sequence=(List<?>)values.get(role);
            int index=positions.getOrDefault(role,0);
            if (sequence==null || index>=sequence.size()) throw new IllegalStateException("feed exhausted: "+role);
            double value=((Number)sequence.get(index)).doubleValue();
            positions.put(role,index+1); calls.add(row("role",role,"value",value));
            return value;
        }
    }
    static final class Real extends AbstractRealSampler {
        final String role; final Feed feed;
        Real(String role, Feed feed) { this.role=role; this.feed=feed; }
        public double next(RandomDataGenerator rng) { return feed.next(role,rng); }
        public void setLower(double v) {} public void setUpper(double v) {}
        public void setMean(double v) {
            if (role.equals("inter_release_time") && v!=100) throw new IllegalStateException("unexpected compatibility mean");
        }
        public double getMean() { return 100; }
        public AbstractRealSampler clone() { return new Real(role,feed); }
    }
    static final class IntegerFeed extends AbstractIntegerSampler {
        final Feed feed; IntegerFeed(Feed feed) { this.feed=feed; }
        public int next(RandomDataGenerator rng) { return (int)feed.next("workflow_type",rng); }
        public void setLower(int v) {} public void setUpper(int v) {} public void setMean(double v) {}
        public double getMean() { return 0; }
        public AbstractIntegerSampler clone() { return new IntegerFeed(feed); }
    }
    static String rid(Server server, SystemState state) {
        int localIndex=0;
        for (Server current:state.getServers()) {
            if (current==server) return (server.getType()==ServerType.EDGE?"E":"C")+localIndex;
            if (current.getType()==server.getType()) localIndex++;
        }
        throw new IllegalStateException("foreign server");
    }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        Map<String,Object> request=(Map<String,Object>)Json.parse(Files.readString(Path.of(args[0])));
        Feed feed=new Feed((Map<String,Object>)request.get("role_values"));
        Map<String,Object> cfg=(Map<String,Object>)request.get("environment");
        int mobiles=((Number)cfg.get("num_mobile_devices")).intValue();
        int edges=((Number)cfg.get("num_edge_servers")).intValue();
        int clouds=((Number)cfg.get("num_cloud_servers")).intValue();
        boolean local=(Boolean)cfg.get("can_mobile_devices_process_tasks");
        DynamicSimulation sim=new DynamicSimulation(7,null,null,10,0,mobiles,edges,clouds,
            new Real("workload",feed),new Real("data_size",feed),new Real("edge_data",feed),
            new Real("inter_release_time",feed),new Real("weight",feed),
            new Real("upload_bandwidth_cloud",feed),new Real("download_bandwidth_cloud",feed),
            new Real("upload_bandwidth_edge",feed),new Real("download_bandwidth_edge",feed),
            new Real("processing_rate_cloud",feed),new Real("processing_rate_edge",feed),
            new Real("processing_rate_device",feed),new IntegerFeed(feed),local);
        SystemState state=sim.getSystemState();
        if (request.get("extra_clock")!=null) {
            state.setClockTime(((Number)request.get("extra_clock")).doubleValue());
            state.getMobileDevices().get(0).generateWorkflowJob();
        }
        List<Object> devices=new ArrayList<>(), servers=new ArrayList<>(), jobs=new ArrayList<>();
        for (MobileDevice device:state.getMobileDevices()) devices.add(row("id","M"+device.getId(),
            "numeric_id",device.getId(),"processing_rate",device.getProcessingRate(),"can_process_tasks",device.isCanProcessTask()));
        for (Server server:state.getServers()) servers.add(row("id",rid(server,state),"numeric_id",server.getId(),
            "type",server.getType().toString(),"processing_rate",server.getProcessingRate(),
            "upload_bandwidth",server.getUploadBandwidth(),"download_bandwidth",server.getDownloadBandwidth()));
        List<String> names=new ArrayList<>();
        for (Element node:new SAXBuilder().build("dax/CyberShake_30.xml").getRootElement().getChildren())
            if (node.getName().equalsIgnoreCase("job")) names.add(node.getAttributeValue("id"));
        for (Job job:state.getJobsInSystem()) {
            List<Object> tasks=new ArrayList<>();
            for (Task task:job.getTaskList()) {
                List<Object> options=new ArrayList<>();
                for (TaskOption option:task.getTaskOptions()) options.add(row("resource_id",
                    option.getServer()==null?"M"+option.getMobileDevice().getId():rid(option.getServer(),state),
                    "processing_time",option.getProcTime(),"upload_time",option.getUploadDelay(),"download_time",option.getDownloadDelay()));
                tasks.add(row("id",names.get(task.getId()),"java_index",task.getId(),"workload",task.getWorkload(),
                    "data_size",task.getData(),"total_input_data",task.getAllInputDataTotal(),
                    "total_output_data",task.getAllOutputDataTotal(),"options",options));
            }
            jobs.add(row("id",job.getId(),"owner_device_id","M"+job.getMobileDevice().getId(),
                         "release_time",job.getReleaseTime(),"weight",job.getWeight(),"tasks",tasks));
        }
        Field eventQueue=MobileDevice.class.getDeclaredField("eventQueue"); eventQueue.setAccessible(true);
        List<Integer> staged=new ArrayList<>();
        for (MobileDevice device:state.getMobileDevices()) staged.add(((Collection<?>)eventQueue.get(device)).size());
        Map<String,Object> output=row("devices",devices,"servers",servers,"accepted_workflows",jobs,
            "calls",feed.calls,"generated_total",state.getAllNumJobsReleased(),"staged_arrivals",staged,
            "clock_time",state.getClockTime(),"shared_input_rng",true);
        Files.writeString(Path.of(args[1]),Json.write(output)+"\n");
    }
}
