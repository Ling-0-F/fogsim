package fogsim.adapter;

import java.nio.file.*;
import java.util.*;
import java.util.function.DoubleSupplier;
import org.jdom2.Element;
import org.jdom2.input.SAXBuilder;
import org.apache.commons.math3.random.RandomDataGenerator;
import mengxu.taskscheduling.Task;
import mengxu.taskscheduling.WorkflowParser;
import mengxu.taskscheduling.dag.DAGType;
import mengxu.taskscheduling.dag.DAGTypePath;
import mengxu.util.random.*;

/** Read-only observer of ORIGINAL parser and sampler classes, without overlays.
 * No dynamic simulation, scheduler, environment constructor, or GP execution.
 */
public final class Step2Oracle {
    private static Map<String,Object> row(Object... fields) {
        Map<String,Object> out = new LinkedHashMap<>();
        for (int i = 0; i < fields.length; i += 2) out.put((String)fields[i], fields[i+1]);
        return out;
    }

    private static List<String> refs(List<Task> tasks, List<String> ids) {
        List<String> out = new ArrayList<>();
        for (Task task : tasks) out.add(ids.get(task.getId()));
        return out;
    }

    private static List<Object> topology(Path root) throws Exception {
        List<Object> out = new ArrayList<>();
        for (DAGType type : DAGType.values()) {
            String filename = Path.of(DAGTypePath.getDAGTypePathForSubmit(type.value)).getFileName().toString();
            Path path = root.resolve(filename);
            // Original parser drops its XML-name map after parsing. Observe job
            // names independently, then pair by ORIGINAL task list position/ID.
            List<String> ids = new ArrayList<>();
            for (Element node : new SAXBuilder().build(path.toFile()).getRootElement().getChildren())
                if (node.getName().equalsIgnoreCase("job")) ids.add(node.getAttributeValue("id"));
            List<Task> tasks = new WorkflowParser(path.toString()).getTaskList();
            if (tasks.size() != ids.size() || tasks.isEmpty()) throw new IllegalStateException("parser failed: " + filename);
            List<Object> rows = new ArrayList<>();
            for (int i = 0; i < tasks.size(); i++) {
                Task task = tasks.get(i);
                if (task.getId() != i) throw new IllegalStateException("unexpected Java task index");
                rows.add(row("xml_id", ids.get(i), "java_index", task.getId(),
                    "parents", refs(task.getParentTaskList(), ids), "children", refs(task.getChildTaskList(), ids)));
            }
            out.add(row("dag_type_id", type.value, "filename", filename, "tasks", rows));
        }
        return out;
    }

    private static Map<String,Object> statistics(DoubleSupplier sampler, boolean discrete, int count) {
        double sum = 0, sumsq = 0, min = Double.POSITIVE_INFINITY, max = Double.NEGATIVE_INFINITY;
        int belowMean100 = 0;
        Map<String,Object> frequencies = new LinkedHashMap<>();
        for (int i = 0; i < count; i++) {
            double value = sampler.getAsDouble();
            if (!Double.isFinite(value)) throw new IllegalStateException("non-finite sample");
            sum += value; sumsq += value * value;
            min = Math.min(min, value); max = Math.max(max, value);
            if (value <= 100) belowMean100++;
            if (discrete) {
                String key = Double.toString(value);
                frequencies.put(key, ((Integer)frequencies.getOrDefault(key, 0)) + 1);
            }
        }
        double mean = sum / count;
        return row("mean", mean, "variance", sumsq / count - mean * mean,
            "minimum", min, "maximum", max, "cdf_at_100", (double)belowMean100 / count, "counts", frequencies);
    }

    private static List<Object> distributions() {
        List<Object> out = new ArrayList<>();
        Map<String,AbstractRealSampler> roles = new LinkedHashMap<>();
        roles.put("workload", new UniformSampler(5000, 15000));
        roles.put("data_size", new UniformSampler(5120, 20480));
        roles.put("edge_data", new UniformSampler(100, 200));
        roles.put("processing_rate_device", new UniformSampler(125, 250));
        roles.put("processing_rate_edge", new UniformSampler(250, 500));
        roles.put("processing_rate_cloud", new UniformSampler(500, 1000));
        roles.put("inter_release_time", new ExponentialSampler(100));
        roles.put("weight", new TwoSixTwoSampler());
        roles.put("upload_bandwidth_cloud", new BandwidthCloudSampler());
        roles.put("download_bandwidth_cloud", new BandwidthCloudSampler());
        roles.put("upload_bandwidth_edge", new BandwidthEdgeSampler());
        roles.put("download_bandwidth_edge", new BandwidthEdgeSampler());
        for (long seed : new long[]{0, 1, 20261104}) {
            for (Map.Entry<String,AbstractRealSampler> entry : roles.entrySet()) {
                RandomDataGenerator rdg = new RandomDataGenerator(); rdg.reSeed(seed);
                String role = entry.getKey();
                boolean discrete = role.equals("weight") || role.contains("bandwidth");
                out.add(row("seed", seed, "role", role, "samples", 100000,
                    "statistics", statistics(() -> entry.getValue().next(rdg), discrete, 100000)));
            }
            for (int upper : new int[]{19, 0}) {
                RandomDataGenerator rdg = new RandomDataGenerator(); rdg.reSeed(seed);
                UniformIntegerSampler sampler = new UniformIntegerSampler(0, upper);
                out.add(row("seed", seed, "role", upper == 0 ? "integer_singleton" : "workflow_type", "samples", 100000,
                    "statistics", statistics(() -> sampler.next(rdg), true, 100000)));
            }
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        Map<String,Object> output = row("scope", "original-parser-and-samplers-only",
            "topology", topology(Path.of(args[0])), "distributions", distributions());
        Files.writeString(Path.of(args[1]), Json.write(output) + "\n");
    }
}
