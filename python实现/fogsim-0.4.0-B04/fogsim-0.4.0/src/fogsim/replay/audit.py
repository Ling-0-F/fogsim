"""Independent binary64 audit of cumulative values and formulas; never mutates inputs."""
import struct
from fogsim.environment.spec import DeviceSnapshot


def audit_formulas(replay_input):
    archive = replay_input.archive
    resources = {r.id: r for r in (*archive.environment.devices, *archive.environment.servers)}
    templates = {t.ref: t for t in archive.templates}
    differences = []
    def check(record, task, field, actual, expected):
        if struct.pack('>d', actual) != struct.pack('>d', expected):
            # Nonfinite derived expectations are diagnostic text, never invalid JSON.
            differences.append(dict(record_id=record, task_id=task, field=field,
                recorded=actual, calculated=expected if abs(expected) != float('inf') else str(expected)))
    for record in archive.candidates:
        w = record.workflow_input
        parents, children = templates[w.template_ref].adjacency()
        edges = {(e.parent_id,e.child_id):e.data_size for e in w.edges}
        for t in w.tasks:
            ti = to = 0.0
            for parent in parents[t.id]: ti += edges[parent,t.id]
            for child in children[t.id]: to += edges[t.id,child]
            check(record.record_id,t.id,'total_input_data',t.total_input_data,ti)
            check(record.record_id,t.id,'total_output_data',t.total_output_data,to)
            for o in t.options:
                r = resources[o.resource_id]
                for field, expected in (('processing_time', t.workload/r.processing_rate),
                    ('upload_time',0.0 if isinstance(r,DeviceSnapshot) else (t.data_size+ti)/r.upload_bandwidth),
                    ('download_time',0.0 if isinstance(r,DeviceSnapshot) else (t.data_size+to)/r.download_bandwidth)):
                    check(record.record_id,t.id,o.resource_id+'.'+field,getattr(o,field),expected)
    return dict(passed=not differences, differences=differences, authority='recorded durations; audit never rewrites them')
