package fogsim.adapter;

import java.lang.reflect.Field;
import java.nio.file.*;
import java.util.*;
import mengxu.rule.RuleType;
import mengxu.simulation.DynamicSimulation;
import mengxu.util.random.*;

/** Separate fresh-run entry to ORIGINAL constructor/setup/run and native metrics. */
public final class StageDDynamicMain {
    static AbstractRealSampler real(String role,AbstractRealSampler delegate) {
        return StageDDynamicCapture.current.mode.equals("plain")?delegate:new StageDDynamicCapture.Real(role,delegate);
    }
    static AbstractIntegerSampler workflow(Map<String,Object> r,String mode) {
        AbstractIntegerSampler sampler=new UniformIntegerSampler(((Number)r.get("min_type")).intValue(),((Number)r.get("max_type")).intValue());
        return mode.equals("plain")?sampler:new StageDDynamicCapture.IntegerSampler(sampler);
    }
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        Map<String,Object> r=(Map<String,Object>)Json.parse(Files.readString(Path.of(args[0])));
        String mode=args[1]; Path directory=Path.of(args[2]); Files.createDirectories(directory);
        if(!List.of("plain","baseline","minimal","full").contains(mode)) throw new IllegalArgumentException("unknown mode");
        StageDDynamicCapture c=new StageDDynamicCapture(mode,r,directory); StageDDynamicCapture.current=c;
        Map<String,Object> effective=StageDGP.obj(r.get("effective_config")),origin=StageDGP.obj(StageDGP.obj(r.get("origin")).get("rules"));
        for(String role:List.of("routing","sequencing")) {
            if(!r.get(role+"_rule").equals(effective.get(role+"_rule"))||!r.get(role+"_rule").equals(origin.get(role)))
                throw new IllegalArgumentException("GP_RULE_IDENTITY_MISMATCH: request rule sources differ");
        }
        int devices=((Number)r.get("devices")).intValue(),edges=((Number)r.get("edges")).intValue(),clouds=((Number)r.get("clouds")).intValue();
        if(devices<1||edges<0||clouds<0||(!(Boolean)r.get("local")&&edges+clouds==0)) throw new IllegalArgumentException("no eligible resources");
        Map<String,Object> routing=StageDGP.obj(r.get("routing_rule"));
        if("fixed_resource".equals(routing.get("kind"))) {
            Set<String> eligible=new HashSet<>();
            for(int i=0;i<edges;i++)eligible.add("E"+i);
            for(int i=0;i<clouds;i++)eligible.add("C"+i);
            if(devices==1&&(Boolean)r.get("local"))eligible.add("M0");
            if(!eligible.contains(routing.get("resource_id")))throw new IllegalArgumentException("fixed target ineligible before RNG construction");
        }
        // Verify supplied metadata from actual XML and the original Java parser;
        // the capture never guesses IDs from numeric suffixes.
        for(Object item:(List<?>)r.get("templates")) {
            Map<String,Object> t=(Map<String,Object>)item;
            Path xml=Path.of("dax",(String)t.get("source_name"));
            if(!StageDDynamicCapture.hash(Files.readAllBytes(xml)).equals(t.get("source_sha256")))
                throw new IllegalArgumentException("DAX fingerprint mismatch");
            List<String> names=new ArrayList<>();
            for(org.jdom2.Element node:new org.jdom2.input.SAXBuilder().build(xml.toFile()).getRootElement().getChildren())
                if(node.getName().equalsIgnoreCase("job")) names.add(node.getAttributeValue("id"));
            List<mengxu.taskscheduling.Task> tasks=new mengxu.taskscheduling.WorkflowParser(xml.toString()).getTaskList();
            if(tasks.size()!=((List<?>)t.get("tasks")).size()) throw new IllegalArgumentException("task count mismatch");
            List<List<String>> dependencies=new ArrayList<>();
            for(Object edge:(List<?>)t.get("dependencies")) dependencies.add((List<String>)edge);
            for(int i=0;i<tasks.size();i++) {
                if(!names.get(i).equals(StageDDynamicCapture.xmlID(t,i))) throw new IllegalArgumentException("XML ID mapping mismatch");
                List<String> parents=new ArrayList<>(),children=new ArrayList<>(),expectedParents=new ArrayList<>(),expectedChildren=new ArrayList<>();
                for(mengxu.taskscheduling.Task p:tasks.get(i).getParentTaskList()) parents.add(names.get(p.getId()));
                for(mengxu.taskscheduling.Task child:tasks.get(i).getChildTaskList()) children.add(names.get(child.getId()));
                for(List<String> edge:dependencies) {
                    if(edge.get(0).equals(names.get(i))) expectedChildren.add(edge.get(1));
                    if(edge.get(1).equals(names.get(i))) expectedParents.add(edge.get(0));
                }
                if(!parents.equals(expectedParents)||!children.equals(expectedChildren)) throw new IllegalArgumentException("Java adjacency mapping mismatch");
            }
        }
        long seed=((Number)r.get("seed")).longValue();
        DynamicSimulation sim=new DynamicSimulation(seed,mode.equals("plain")?c.prepared.rules.get("sequencing"):new StageDDynamicCapture.AuditRule(RuleType.SEQUENCING),
            mode.equals("plain")?c.prepared.rules.get("routing"):new StageDDynamicCapture.AuditRule(RuleType.ROUTING),((Number)r.get("N")).intValue(),((Number)r.get("W")).intValue(),
            ((Number)r.get("devices")).intValue(),((Number)r.get("edges")).intValue(),((Number)r.get("clouds")).intValue(),
            real("workload",new UniformSampler(5000,15000)),real("data_size",new UniformSampler(5120,20480)),
            real("edge_data",new UniformSampler(100,200)),real("inter_release_time",new ExponentialSampler()),
            real("weight",new TwoSixTwoSampler()),real("upload_bandwidth_cloud",new BandwidthCloudSampler()),
            real("download_bandwidth_cloud",new BandwidthCloudSampler()),real("upload_bandwidth_edge",new BandwidthEdgeSampler()),
            real("download_bandwidth_edge",new BandwidthEdgeSampler()),real("processing_rate_cloud",new UniformSampler(500,1000)),
            real("processing_rate_edge",new UniformSampler(250,500)),real("processing_rate_device",new UniformSampler(125,250)),
            workflow(r,mode),(Boolean)r.get("local"));
        StageDGP.RESOURCE_IDS.clear();
        for(mengxu.taskscheduling.MobileDevice d:sim.getSystemState().getMobileDevices()) StageDGP.RESOURCE_IDS.put(d,"M"+d.getId());
        for(mengxu.taskscheduling.Server server:sim.getSystemState().getServers()) StageDGP.RESOURCE_IDS.put(server,StageDDynamicCapture.serverID(server,sim.getSystemState()));
        // Global queue is empty until original run() performs its first merge.
        // AuditQueue delegates poll once to PriorityQueue and does not change
        // comparator, insertion, iteration, capacity behavior or event objects.
        if(!sim.getEventQueue().isEmpty()) throw new IllegalStateException("unexpected pre-run global events");
        Field queue=DynamicSimulation.class.getDeclaredField("eventQueue"); queue.setAccessible(true);
        if(!mode.equals("plain")) queue.set(sim,new StageDDynamicCapture.AuditQueue());
        try {
            sim.run(); c.finish(sim,true,"JAVA_RUN_RETURNED");
        } catch(Exception | Error ex) {
            c.finish(sim,false,ex.getClass().getName()); throw ex;
        }
    }
}
