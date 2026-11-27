"""Run extracted, unmodified Java methods against the Python components.

Not a Java scheduler adapter. Model stubs only provide values read by the methods.
Extraction hashes, operation input, raw outputs and JDK version are retained.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import zipfile
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fogsim.simulation.events import JobArrivalEvent, TaskVisitEvent, ProcessStartEvent, ProcessFinishEvent
from fogsim.simulation.event_queue import JavaPriorityQueue, compare_event_java
from fogsim.model.resource import ResourceType, MobileDevice, Server
from fogsim.model.task import Task, TaskOption
from fogsim.model.workflow import Workflow
from fogsim.rules.selection import double_compare, is_preferred

JAVA_ROOT = ROOT / "references/java/Fog-Computing-multiDeviceDebug/src/mengxu"


def extract_method(path, signature, manifest):
    content = path.read_text(encoding="utf-8")
    start = content.index(signature)
    end = content.index("{", start) + 1
    depth = 1
    while depth:
        if content[end] == "{": depth += 1
        elif content[end] == "}": depth -= 1
        end += 1
    method = content[start:end]
    manifest.append({"source": str(path.relative_to(ROOT)).replace("\\", "/"),
        "signature": signature, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "method_utf8_sha256": hashlib.sha256(method.encode()).hexdigest()})
    return method


def build_java():
    manifest = []
    source = r'''
import java.util.*;
import java.nio.file.*;
public class ComponentOracle {
 static abstract class AbstractEvent implements Comparable<AbstractEvent> {
   double time; String label;
 }
 static class Job {
   int id; double release; MobileDevice mobile;
   int getId(){return id;} double getReleaseTime(){return release;}
   MobileDevice getMobileDevice(){return mobile;}
 }
 static class Task { Job job; Job getJob(){return job;} }
 static class Process {
   Server server; TaskOption option;
   Server getServer(){return server;} TaskOption getTaskOption(){return option;}
 }
'''
    for cls in ("JobArrivalEvent", "ProcessStartEvent", "TaskVisitEvent", "ProcessFinishEvent"):
        method = extract_method(JAVA_ROOT/f"simulation/event/{cls}.java", "public int compareTo(AbstractEvent other)", manifest)
        source += f"static class {cls} extends AbstractEvent {{\n"
        source += "Job job; Process process; Process getProcess(){return process;}\n" + method + "\n}\n"
    source += "static class TaskOption { Task task; double priority,pt,ut,dt; Task getTask(){return task;} double getProcTime(){return pt;} double getUploadDelay(){return ut;} double getDownloadDelay(){return dt;}\n"
    source += extract_method(JAVA_ROOT/"taskscheduling/TaskOption.java", "public boolean priorTo(TaskOption other)", manifest) + "\n}\n"
    for cls in ("MobileDevice", "Server"):
        source += f"static class {cls} {{ int id; int getId(){{return id;}} LinkedList<TaskOption> queue=new LinkedList<>(); double totalProcTimeInQueue=0.0, totalProcTimeAndUpLoadAndDownLoadTimeInQueue=0.0;\n"
        for sig in ("public void addToQueue", "public void removeFromQueue", "public double totalProcTimeInQueue()", "public double totalProcTimeAndUpLoadAndDownLoadTimeInQueue()"):
            source += extract_method(JAVA_ROOT/f"taskscheduling/{cls}.java", sig, manifest) + "\n"
        source += "}\n"
    source += r'''
 static TaskOption option(double priority,double release,int owner,int job){
   TaskOption o=new TaskOption();o.priority=priority;o.task=new Task();o.task.job=new Job();
   o.task.job.id=job;o.task.job.release=release;o.task.job.mobile=new MobileDevice();o.task.job.mobile.id=owner;return o;
 }
 static AbstractEvent event(String label,int kind,double time,int wid,int owner,boolean local,int server){
   TaskOption o=option(0,0,owner,wid);Process p=new Process();p.option=o;
   if(!local){p.server=new Server();p.server.id=server;}
   AbstractEvent e;
   if(kind==0){JobArrivalEvent a=new JobArrivalEvent();a.job=o.task.job;e=a;}
   else if(kind==1){ProcessStartEvent a=new ProcessStartEvent();a.process=p;e=a;}
   else if(kind==2){TaskVisitEvent a=new TaskVisitEvent();a.process=p;e=a;}
   else{ProcessFinishEvent a=new ProcessFinishEvent();a.process=p;e=a;}
   e.time=time;e.label=label;return e;
 }
 static String bits(double d){return Long.toHexString(Double.doubleToLongBits(d));}
 public static void main(String[] args) throws Exception {
   Map<String,AbstractEvent> events=new HashMap<>();Map<String,TaskOption> options=new HashMap<>();
   Map<String,PriorityQueue<AbstractEvent>> heaps=new HashMap<>();
   List<PriorityQueue<AbstractEvent>> staged=List.of(new PriorityQueue<>(),new PriorityQueue<>(),new PriorityQueue<>());
   PriorityQueue<AbstractEvent> global=new PriorityQueue<>();MobileDevice mobile=new MobileDevice();Server server=new Server();
   for(String line:Files.readAllLines(Path.of(args[0]))){
     String[] v=line.split(" ");String op=v[0];
     if(op.equals("E")){events.put(v[1],event(v[1],Integer.parseInt(v[2]),Double.parseDouble(v[3]),Integer.parseInt(v[4]),Integer.parseInt(v[5]),v[6].equals("1"),Integer.parseInt(v[7])));}
     else if(op.equals("C")){System.out.println("C "+events.get(v[1]).compareTo(events.get(v[2])));}
     else if(op.equals("O")){heaps.computeIfAbsent(v[1],k->new PriorityQueue<>()).offer(events.get(v[2]));}
     else if(op.equals("P")){AbstractEvent e=heaps.get(v[1]).poll();System.out.println("P "+(e==null?"null":e.label));}
     else if(op.equals("S")){staged.get(Integer.parseInt(v[1])).offer(events.get(v[2]));}
     else if(op.equals("N")){
       for(int i=0;i<3;i++){while(!staged.get(i).isEmpty()){
         AbstractEvent e=staged.get(i).poll();System.out.println("SP "+i+" "+e.label);global.offer(e);System.out.println("GO "+e.label);
       }}AbstractEvent e=global.poll();System.out.println("GP "+(e==null?"null":e.label));
     }
     else if(op.equals("D")){System.out.println("D "+Double.compare(Double.parseDouble(v[1]),Double.parseDouble(v[2])));}
     else if(op.equals("T")){options.put(v[1],option(Double.parseDouble(v[2]),Double.parseDouble(v[3]),Integer.parseInt(v[4]),Integer.parseInt(v[5])));}
     else if(op.equals("B")){System.out.println("B "+options.get(v[1]).priorTo(options.get(v[2])));}
     else if(op.equals("K")){
       TaskOption o;
       if(v[2].equals("+")){o=option(0,0,0,0);o.pt=Double.parseDouble(v[4]);o.ut=Double.parseDouble(v[5]);o.dt=Double.parseDouble(v[6]);options.put(v[3],o);}
       else{o=options.get(v[3]);}
       if(v[1].equals("M")){
         if(v[2].equals("+"))mobile.addToQueue(o);else mobile.removeFromQueue(o);
         System.out.println("K "+bits(mobile.totalProcTimeInQueue)+" "+bits(mobile.totalProcTimeAndUpLoadAndDownLoadTimeInQueue)+" "+bits(mobile.totalProcTimeInQueue())+" "+bits(mobile.totalProcTimeAndUpLoadAndDownLoadTimeInQueue()));
       }else{
         if(v[2].equals("+"))server.addToQueue(o);else server.removeFromQueue(o);
         System.out.println("K "+bits(server.totalProcTimeInQueue)+" "+bits(server.totalProcTimeAndUpLoadAndDownLoadTimeInQueue)+" "+bits(server.totalProcTimeInQueue())+" "+bits(server.totalProcTimeAndUpLoadAndDownLoadTimeInQueue()));
       }
     }
   }
 }
}
'''
    return source, manifest


def operation_fixture():
    lines=[]
    # Every ordered pair, including anomalous self/equal-ID comparisons.
    for i in range(24):
        lines.append(f"E e{i} {i%4} 0 {i%3} {i%3} {(i//4)%2} {i%2}")
    for a in range(24):
        for b in range(24):lines.append(f"C e{a} e{b}")
    # Scripted ties and reproducible mixed offer/poll; randomness only creates the oracle fixture.
    rng=random.Random(170016)
    for i in range(24,224):
        lines.append(f"E e{i} {rng.randrange(4)} {rng.randrange(5)} {rng.randrange(8)} {rng.randrange(3)} {rng.randrange(2)} {rng.randrange(4)}")
    for h in range(15):
        size=0
        for _ in range(100):
            if size and rng.random()<0.35:
                lines.append(f"P h{h}");size-=1
            else:
                lines.append(f"O h{h} e{rng.randrange(224)}");size+=1
        lines.extend([f"P h{h}"]*(size+1))
    size=0
    for _ in range(200):
        for _ in range(rng.randrange(4)):
            lines.append(f"S {rng.randrange(3)} e{rng.randrange(224)}");size+=1
        lines.append("N");size=max(0,size-1)
    lines.extend(["N"]*(size+1))
    special=["-Infinity","-1.0","-0.0","0.0","1.0","Infinity","NaN"]
    for a in special:
        for b in special:lines.append(f"D {a} {b}")
    for i in range(35):
        lines.append(f"T t{i} {special[i%7]} {i%3} {i%2} {i%5}")
    for a in range(35):
        for b in range(35):lines.append(f"B t{a} t{b}")
    for kind in ("M","S"):
        for i,pt in enumerate((0.1,0.2,0.3)):
            lines.append(f"K {kind} + {kind}{i} {pt} 0 0")
        for i in (1,0,2):lines.append(f"K {kind} - {kind}{i}")
    # Server nonzero upload/download arithmetic as read from source.
    for i,times in enumerate(((3,2,1),(4,1,2),(0.1,0.2,0.3))):
        lines.append(f"K S + extra{i} {' '.join(map(str,times))}")
    for i in (1,2,0):lines.append(f"K S - extra{i}")
    return lines


def python_output(lines):
    import struct
    events={};options={};heaps={};staged=[JavaPriorityQueue(compare_event_java) for _ in range(3)]
    global_heap=JavaPriorityQueue(compare_event_java);out=[]
    resources={"M":MobileDevice("M",0,ResourceType.MOBILE),"S":Server("S",0,ResourceType.EDGE)}
    labels={}
    def option(priority,release,owner,job):
        d=MobileDevice(str(owner),owner,ResourceType.MOBILE)
        w=Workflow(job,d,release);t=Task("A",w,dispatched=True)
        return TaskOption(t,d,1,0,0,priority=priority)
    def bits(value):return format(struct.unpack(">Q",struct.pack(">d",value))[0],"x")
    for line in lines:
        v=line.split();op=v[0]
        if op=="E":
            name=v[1];kind=int(v[2]);time=float(v[3]);wid,owner,local,server=map(int,v[4:])
            o=option(0,time,owner,wid)
            if not local:o.resource=Server(str(server),server,ResourceType.EDGE)
            ex=NS(task=o.task,option=o,resource=o.resource,start_time=time,finish_time=time)
            e=[lambda:JobArrivalEvent(o.task.workflow),lambda:ProcessStartEvent(ex),
               lambda:TaskVisitEvent(time,o),lambda:ProcessFinishEvent(ex)][kind]()
            events[name]=e;labels[e]=name
        elif op=="C":out.append(f"C {compare_event_java(events[v[1]],events[v[2]])}")
        elif op=="O":heaps.setdefault(v[1],JavaPriorityQueue(compare_event_java)).offer(events[v[2]])
        elif op=="P":out.append("P "+labels.get(heaps[v[1]].poll(),"null"))
        elif op=="S":staged[int(v[1])].offer(events[v[2]])
        elif op=="N":
            for i,h in enumerate(staged):
                while h:
                    e=h.poll();out.append(f"SP {i} {labels[e]}");global_heap.offer(e);out.append(f"GO {labels[e]}")
            out.append("GP "+labels.get(global_heap.poll(),"null"))
        elif op=="D":out.append(f"D {double_compare(float(v[1]),float(v[2]))}")
        elif op=="T":options[v[1]]=option(float(v[2]),float(v[3]),int(v[4]),int(v[5]))
        elif op=="B":out.append("B "+str(is_preferred(options[v[1]],options[v[2]])).lower())
        elif op=="K":
            r=resources[v[1]]
            if v[2]=="+":
                o=option(0,0,0,0);o.resource=r;o.processing_time,o.upload_time,o.download_time=map(float,v[4:])
                options[v[3]]=o;r.enqueue(o)
            else:r.remove_waiting(options[v[3]])
            out.append("K "+" ".join(bits(x) for x in (r.queued_processing_time,r.queued_total_time,r.waiting_processing_time,r.waiting_total_time)))
    return out


def find_java(explicit=None):
    import os
    selected=explicit or os.environ.get("FOGSIM_JAVA")
    if selected:return str(Path(selected).resolve())
    local=ROOT/"references/jdk/jdk-17.0.16+8/bin/java.exe"
    return str(local) if local.exists() else shutil.which("java")


def run_oracle(java=None, output=None):
    java=find_java(java)
    if not java:raise RuntimeError("JDK unavailable; supply --java /path/to/JDK17/bin/java")
    output=Path(output or ROOT/"outputs/java_oracle");output.mkdir(parents=True,exist_ok=True)
    source,methods=build_java()
    source_file=output/"ComponentOracle.java";source_file.write_text(source,encoding="utf-8")
    lines=operation_fixture();fixture=output/"operations.txt";fixture.write_text("\n".join(lines)+"\n",encoding="utf-8")
    from java_support import reference_jdk
    reference=reference_jdk(java)
    (output/"java-version.txt").write_text(reference["version_output"],encoding="utf-8")
    priority_queue_sha=reference["priority_queue_source_sha256"]
    proc=subprocess.run([java,str(source_file),str(fixture)],capture_output=True,text=True,check=True)
    expected=python_output(lines);actual=proc.stdout.splitlines()
    (output/"java-output.txt").write_text(proc.stdout,encoding="utf-8")
    (output/"python-output.txt").write_text("\n".join(expected)+"\n",encoding="utf-8")
    first=next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),None)
    matched=actual==expected
    report={"passed":matched,"jdk_executable":java,"priority_queue_source_sha256":priority_queue_sha,
        "operation_count":len(lines),
        "comparison_output_count":len(actual),"python_output_count":len(expected),
        "first_difference_line":None if matched else (first+1 if first is not None else min(len(actual),len(expected))+1),
        "scope":"Extracted original comparator/priorTo/cache methods and java.util.PriorityQueue; not full simulator parity",
        "methods":methods,"fixture_sha256":hashlib.sha256(fixture.read_bytes()).hexdigest()}
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if not matched:raise AssertionError(f"oracle mismatch: {report['first_difference_line']}")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--java");p.add_argument("--output",type=Path)
    args=p.parse_args();report=run_oracle(args.java,args.output)
    print(json.dumps({k:v for k,v in report.items() if k!="methods"},indent=2))
