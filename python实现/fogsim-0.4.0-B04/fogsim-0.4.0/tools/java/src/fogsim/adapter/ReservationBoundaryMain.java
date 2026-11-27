package fogsim.adapter;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import mengxu.simulation.event.ProcessStartEvent;
import mengxu.taskscheduling.*;
import mengxu.taskscheduling.Process;

/** Isolated, deliberately injected states; NOT full reachable scheduling runs. */
public final class ReservationBoundaryMain {
    public static void main(String[] args) throws Exception {
        Map<String,Object> request = FixedInstanceMain.obj(Json.parse(Files.readString(Path.of(args[0]), StandardCharsets.UTF_8)));
        List<Object> rows = new ArrayList<>();
        for (String scenario : List.of("empty", "staged_only", "matching_root", "matching_below_other_root")) {
            FixedInstanceMain a = new FixedInstanceMain(request);
            for (MobileDevice d : a.state.getMobileDevices()) d.eventQueue.clear();
            a.simulation.getEventQueue().clear();
            FixedInstanceMain.FixedDevice d = (FixedInstanceMain.FixedDevice) a.state.getMobileDevices().get(0);
            TaskOption local = a.tasks.get(0).getTaskOptions().get(0);
            Process pending = new Process(null, local, scenario.equals("matching_below_other_root") ? 1 : 0);
            ProcessStartEvent start = new ProcessStartEvent(pending, d);
            boolean hasPending = !scenario.equals("empty");
            if (hasPending) {
                d.addEvent(start);
                if (!scenario.equals("staged_only")) { d.eventQueue.clear(); a.simulation.getEventQueue().offer(start); }
                if (scenario.equals("matching_below_other_root")) {
                    TaskOption remote = a.tasks.get(0).getTaskOptions().get(1);
                    a.simulation.getEventQueue().offer(new ProcessStartEvent(new Process(remote.getServer(), remote, 0), d));
                }
            }
            Process attempt = new Process(null, a.tasks.get(1).getTaskOptions().get(0), 0);
            boolean original = d.canAddToQueue(attempt);
            rows.add(FixedInstanceMain.map("scenario", scenario, "original_allowed", original,
                "python_reservation_allows", !hasPending, "equal", original == !hasPending,
                "reachable_run", false, "check", a.reservationChecks.get(a.reservationChecks.size()-1)));
        }
        Files.writeString(Path.of(args[1]), Json.write(FixedInstanceMain.map("scope", "injected component states only", "cases", rows))+"\n", StandardCharsets.UTF_8);
    }
}
