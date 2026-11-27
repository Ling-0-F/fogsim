package fogsim.adapter;
import static fogsim.adapter.StageDGP.*;
import java.nio.file.*;
import java.util.*;
import ec.gp.*;
import mengxu.gp.data.DoubleData;
import mengxu.gp.terminal.*;
import mengxu.rule.*;
import mengxu.simulation.*;
import mengxu.simulation.event.*;
import mengxu.taskscheduling.*;
import mengxu.taskscheduling.Process;

/** Fixtures contain physical facts and queue operations, never expected scores. */
public final class StageDProbe {
    static final class Loaded {
        final FixedInstanceMain base;final Map<String,Object> fixture;final Map<String,TaskOption> options=new LinkedHashMap<>();
        Loaded(Map<String,Object> f){fixture=f;RESOURCE_IDS.clear();base=new FixedInstanceMain(map("schema_version",1,"record_trace",false,"input",f.get("instance"),"config",map("max_events",1000,"event_policy","java_compatible","routing_kind","fcfs","sequencing_kind","fcfs")));
            for(Object r:base.resources)RESOURCE_IDS.put(r,base.resourceNames.get(r));
            for(Task t:base.tasks)for(TaskOption o:t.getTaskOptions())options.put(key(base.optionKey(o)),o);
            base.state.setClockTime(((Number)f.get("clock_time")).doubleValue());
            for(Object item:list(f.get("ready_times"))){Map<String,Object>r=obj(item);option(r.get("option")).setReadyTime(((Number)r.get("value")).doubleValue());}
            for(Object item:list(f.get("available_times"))){Map<String,Object>r=obj(item);Object resource=base.resourcesById.get(str(r.get("resource_id")));double v=((Number)r.get("value")).doubleValue();if(resource instanceof MobileDevice)((MobileDevice)resource).setReadyTime(v);else ((Server)resource).setReadyTime(v);}
            for(Object item:list(f.get("queue_history"))){Map<String,Object>h=obj(item);TaskOption o=option(h.get("option"));Object r=base.resource(o);o.getTask().setDispatch(true);
                if("enqueue".equals(h.get("action"))){if(r instanceof MobileDevice)((MobileDevice)r).addToQueue(o);else ((Server)r).addToQueue(o);}
                else if("remove".equals(h.get("action"))){if(r instanceof MobileDevice)((MobileDevice)r).removeFromQueue(o);else ((Server)r).removeFromQueue(o);}
                else throw new IllegalArgumentException("invalid queue history action");}
            for(Object item:list(f.get("completed_options"))){TaskOption o=option(item);o.getTask().setDispatch(true);o.getTask().setComplete(true);Process p=new Process(o.getServer(),o,0.0);o.getTask().getJob().addProcessFinishEvent(new ProcessFinishEvent(p,o.getTask().getJob().getMobileDevice()));}
            for(Object item:list(f.get("pending_starts"))){Map<String,Object>h=obj(item);TaskOption o=option(h.get("option"));o.getTask().setDispatch(true);Process p=new Process(o.getServer(),o,((Number)h.get("start_time")).doubleValue());base.observedPending.get(base.resource(o)).add(p);o.getTask().getJob().getMobileDevice().addEvent(new ProcessStartEvent(p,o.getTask().getJob().getMobileDevice()));}
        }
        String key(Object a){return Json.write(a);}
        TaskOption option(Object key){TaskOption o=options.get(key(key));if(o==null)throw new IllegalArgumentException("unknown option "+key);return o;}
        Map<String,Object> snapshot(){List<Object>rs=new ArrayList<>(),ws=new ArrayList<>();
            for(Object r:base.resources){List<Object>q=new ArrayList<>();for(TaskOption o:base.queue(r))q.add(base.optionKey(o));List<Process>pending=base.observedPending.get(r);rs.add(map("id",base.resourceNames.get(r),"numeric_id",r instanceof MobileDevice?((MobileDevice)r).getId():((Server)r).getId(),"type",r instanceof MobileDevice?"MOBILE":((Server)r).getType().toString(),"available_time",base.available(r),"queued_processing_time",base.wiq(r),"queued_total_time",base.ttiq(r),"waiting_queue",q,"pending_start",pending.isEmpty()?null:base.optionKey(pending.get(0).getTaskOption())));}
            for(Job w:base.jobs){List<Object>ts=new ArrayList<>(),done=new ArrayList<>();for(ProcessFinishEvent e:w.getProcessFinishEvents())done.add(base.taskNames.get(e.getProcess().getTaskOption().getTask()));
                for(Task t:w.getTaskList()){List<Object>os=new ArrayList<>();for(TaskOption o:t.getTaskOptions())os.add(map("resource_id",base.resourceNames.get(base.resource(o)),"processing_time",o.getProcTime(),"upload_time",o.getUploadDelay(),"download_time",o.getDownloadDelay(),"ready_time",o.getReadyTime(),"priority",tag(o.getPriority())));ts.add(map("id",base.taskNames.get(t),"dispatched",t.isDispatch(),"completed",t.isComplete(),"options",os));}
                ws.add(map("id",w.getId(),"owner_device_id",base.resourceNames.get(w.getMobileDevice()),"release_time",w.getReleaseTime(),"completed_records",done,"tasks",ts));}
            return map("clock_time",base.state.getClockTime(),"resources",rs,"workflows",ws);
        }
    }
    static Map<String,Object> run(Map<String,Object> c){String id=str(c.get("id")),mode=str(c.get("mode"));
        if(mode.equals("cj")){try{return map("id",id,"status","OK","canonical",cj(c.get("payload")));}catch(IllegalArgumentException e){return map("id",id,"status","REJECTED");}}
        if(mode.equals("f64")){try{return map("id",id,"status","OK","value",tag(f64(c.get("value"))));}catch(IllegalArgumentException e){return map("id",id,"status","REJECTED");}}
        if(mode.equals("parse")){String text=str(c.get("expression"));try{GPNode root=parse(text,(String)c.get("role"),str(c.get("field_path")));List<Object>classes=new ArrayList<>();for(GPNode n:nodes(root))classes.add(n.getClass().getName());return map("id",id,"status","OK","expression",expression(root),"loaded_node_classes",classes);}catch(ParseError e){return map("id",id,"status","PARSE_ERROR","diagnostic",e.diagnostic);}}
        if(mode.equals("manifest")){Prepared p=new Prepared(obj(c.get("routing_rule")),obj(c.get("sequencing_rule")));return map("id",id,"status","OK","rule_manifest",p.manifest);}
        if(mode.equals("function")){GPNode root=op(str(c.get("op")));root.children=new GPNode[]{new ReadConstant(f64(c.get("a"))),new ReadConstant(f64(c.get("b")))};IdentityHashMap<GPNode,Integer> ids=new IdentityHashMap<>();List<GPNode> ns=nodes(root);for(int i=0;i<ns.size();i++)ids.put(ns.get(i),i);NODE_IDS.set(ids);READS.set(new ArrayList<>());DoubleData d=new DoubleData();try{root.eval(null,0,d,null,null,null);return map("id",id,"status","OK","value",tag(d.value),"reads",new ArrayList<>(READS.get()));}finally{READS.remove();NODE_IDS.remove();}}
        if(!mode.equals("state"))throw new IllegalArgumentException("unknown probe mode");
        Loaded l=new Loaded(obj(c.get("fixture")));Prepared p=new Prepared(obj(c.get("routing_rule")),obj(c.get("sequencing_rule")));String role=str(c.get("role"));
        List<TaskOption>cs=new ArrayList<>();for(Object k:list(c.get("candidates")))cs.add(l.option(k));
        Map<String,Object>before=l.snapshot();List<Object>features=new ArrayList<>();for(TaskOption o:cs){Map<String,Object>values=new LinkedHashMap<>();for(String name:FEATURE_NAMES){AttributeGPNode n=new AttributeGPNode(JobShopAttribute.get(name));DoubleData d=new DoubleData();n.eval(null,0,d,null,null,new mengxu.gp.CalcPriorityProblem(o,o.getServer(),l.base.state));values.put(name,tag(d.value));}features.add(map("option",l.base.optionKey(o),"values",values));}
        List<Object>scores=new ArrayList<>(),reads=new ArrayList<>();AbstractRule delegate=p.rules.get(role);
        AbstractRule observed=new AbstractRule(){ {type=role.equals("routing")?RuleType.ROUTING:RuleType.SEQUENCING;} public double priority(TaskOption o,Server server,mengxu.simulation.state.SystemState s){p.begin(role);double v;try{v=delegate.priority(o,server,s);}finally{reads.add(map("option",l.base.optionKey(o),"reads",p.end()));}scores.add(map("option",l.base.optionKey(o),"priority",tag(v)));return v;}};
        Map<String,Object>pureAfter=l.snapshot();TaskOption chosen=role.equals("routing")?observed.nextTaskOption(new RoutingDecisionSituation(cs,l.base.state)):observed.priorTask(new SequencingDecisionSituation(cs,cs.get(0).getServer(),l.base.state));
        return map("id",id,"status","OK","rule_manifest",p.manifest,"loaded",before,"after_features",pureAfter,"features",features,"reads",reads,"scores",scores,"selected",l.base.optionKey(chosen),"selected_is_candidate",cs.stream().anyMatch(x->x==chosen),"after_selection",l.snapshot(),"rng_is_null",l.base.simulation.randomDataGenerator==null&&l.base.state.getMobileDevices().stream().allMatch(d->d.randomDataGenerator==null));
    }
    public static void main(String[]args)throws Exception{Map<String,Object>r=obj(Json.parse(Files.readString(Path.of(args[0]))));if(!"fogsim.gp-probe-input".equals(r.get("format"))||!Long.valueOf(1).equals(r.get("schema_version")))throw new IllegalArgumentException("invalid probe input");List<Object>out=new ArrayList<>();for(Object c:list(r.get("cases"))){try{out.add(run(obj(c)));}finally{RESOURCE_IDS.clear();READS.remove();NODE_IDS.remove();}}Files.writeString(Path.of(args[1]),Json.write(map("format","fogsim.gp-probe-output","schema_version",1,"numeric_semantics_version",NUM,"cases",out))+"\n");}
}
