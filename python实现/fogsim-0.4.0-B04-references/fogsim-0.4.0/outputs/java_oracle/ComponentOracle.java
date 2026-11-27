
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
static class JobArrivalEvent extends AbstractEvent {
Job job; Process process; Process getProcess(){return process;}
public int compareTo(AbstractEvent other) {
        if (time < other.time)
            return -1;

        if (time > other.time)
            return 1;

        if (other instanceof JobArrivalEvent) {
            JobArrivalEvent otherJAE = (JobArrivalEvent)other;

            if (job.getId() < otherJAE.job.getId())
                return -1;

            if (job.getId() > otherJAE.job.getId())
                return 1;
        }

        return -1;
    }
}
static class ProcessStartEvent extends AbstractEvent {
Job job; Process process; Process getProcess(){return process;}
public int compareTo(AbstractEvent other) {
        if (time < other.time)
            return -1;

        if (time > other.time)
            return 1;

        if (other instanceof ProcessStartEvent)
            return 0;

        if (other instanceof ProcessFinishEvent)
            return -1;

        //modified version
        if (other instanceof TaskVisitEvent)
            return -1; //todo: notice, modified part one. Totally two parts are modified.

        return 1;
    }
}
static class TaskVisitEvent extends AbstractEvent {
Job job; Process process; Process getProcess(){return process;}
public int compareTo(AbstractEvent other) {
        if (time < other.time)
            return -1;

        if (time > other.time)
            return 1;

        if (other instanceof JobArrivalEvent)
            return 1;

        if (other instanceof TaskVisitEvent)
            return 0;


        //modified version
        if (other instanceof ProcessStartEvent)
            return 1; //todo: notice, modified part two. Totally two parts are modified.


        return -1;
    }
}
static class ProcessFinishEvent extends AbstractEvent {
Job job; Process process; Process getProcess(){return process;}
public int compareTo(AbstractEvent other) {
        if (time < other.time)
            return -1;

        if (time > other.time)
            return 1;

        if (other instanceof ProcessFinishEvent) {
            ProcessFinishEvent otherPFE = (ProcessFinishEvent)other;

            if(process.getServer() == null && otherPFE.getProcess().getServer() == null){
                if(process.getTaskOption().getTask().getJob().getMobileDevice().getId() < otherPFE.process.getTaskOption().getTask().getJob().getMobileDevice().getId()){
                    return -1;
                }
                if(process.getTaskOption().getTask().getJob().getMobileDevice().getId() > otherPFE.process.getTaskOption().getTask().getJob().getMobileDevice().getId()){
                    return 1;
                }
            }
            else if(process.getServer() == null && otherPFE.getProcess().getServer() != null){
                return -1;
            }
            else if(process.getServer() != null && otherPFE.getProcess().getServer() == null){
                return 1;
            }
            else{
                if (process.getServer().getId() < otherPFE.process.getServer().getId())
                    return -1;

                if (process.getServer().getId() > otherPFE.process.getServer().getId())
                    return 1;
            }

        }

        return 1;
    }
}
static class TaskOption { Task task; double priority,pt,ut,dt; Task getTask(){return task;} double getProcTime(){return pt;} double getUploadDelay(){return ut;} double getDownloadDelay(){return dt;}
public boolean priorTo(TaskOption other) {
        if (Double.compare(priority, other.priority) < 0)
            return true;

        if (Double.compare(priority, other.priority) > 0)
            return false;

        if(task.getJob().getReleaseTime() < other.task.getJob().getReleaseTime())
            return true;

        if(task.getJob().getReleaseTime() > other.task.getJob().getReleaseTime())
            return false;

        if(task.getJob().getMobileDevice().getId() < other.task.getJob().getMobileDevice().getId())
            return true;

        if(task.getJob().getMobileDevice().getId() > other.task.getJob().getMobileDevice().getId())
            return false;

        if(task.getJob().getId() > other.task.getJob().getId())
            return false;

        return task.getJob().getId() < other.task.getJob().getId();
    }
}
static class MobileDevice { int id; int getId(){return id;} LinkedList<TaskOption> queue=new LinkedList<>(); double totalProcTimeInQueue=0.0, totalProcTimeAndUpLoadAndDownLoadTimeInQueue=0.0;
public void addToQueue(TaskOption taskOption){
        this.queue.add(taskOption);
        this.totalProcTimeInQueue += taskOption.getProcTime();
        this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue += (taskOption.getProcTime() + taskOption.getUploadDelay() + taskOption.getDownloadDelay());
    }
public void removeFromQueue(TaskOption o) {
        queue.remove(o);
//        numTasksCompleted++;
        this.totalProcTimeInQueue -= o.getProcTime();
        this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue -= (o.getProcTime() + o.getUploadDelay() + o.getDownloadDelay());
    }
public double totalProcTimeInQueue(){
        return this.totalProcTimeInQueue;
//        double time = 0;
//        for(TaskOption taskOption:queue){
//            time += taskOption.getProcTime();
//        }
//        return time;
    }
public double totalProcTimeAndUpLoadAndDownLoadTimeInQueue(){
        return this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue;
//        double time = 0;
//        for(TaskOption taskOption:queue){
//            time += taskOption.getProcTime() + taskOption.getUploadDelay() + taskOption.getDownloadDelay();
//        }
//        return time;
    }
}
static class Server { int id; int getId(){return id;} LinkedList<TaskOption> queue=new LinkedList<>(); double totalProcTimeInQueue=0.0, totalProcTimeAndUpLoadAndDownLoadTimeInQueue=0.0;
public void addToQueue(TaskOption taskOption){
        this.queue.add(taskOption);
        this.totalProcTimeInQueue += taskOption.getProcTime();
        this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue += (taskOption.getProcTime() + taskOption.getUploadDelay() + taskOption.getDownloadDelay());
    }
public void removeFromQueue(TaskOption o) {
        this.queue.remove(o);
//        numTasksCompleted++;
        if(this.queue.isEmpty()){
            this.totalProcTimeInQueue = 0.0;
            this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue = 0.0;
        }
        else{
            this.totalProcTimeInQueue -= o.getProcTime();
            this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue -= (o.getProcTime() + o.getUploadDelay() + o.getDownloadDelay());
        }
    }
public double totalProcTimeInQueue(){
        if(this.totalProcTimeInQueue<0){
            System.out.println("Error, totalProcTimeInQueue could not lower than 0!!!");
            System.out.println(this.totalProcTimeInQueue);
        }
        if(this.queue.size()==0){
            return 0;
        }
        return this.totalProcTimeInQueue;
    }
public double totalProcTimeAndUpLoadAndDownLoadTimeInQueue(){
        if(this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue<0){
            System.out.println("Error, totalProcTimeAndUpLoadAndDownLoadTimeInQueue could not lower than 0!!!");
            System.out.println(this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue);
        }
        if(this.queue.size()==0){
            return 0;
        }
        return this.totalProcTimeAndUpLoadAndDownLoadTimeInQueue;
    }
}

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
