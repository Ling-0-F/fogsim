"""Strict ordered parser for the project's DAX topology subset; no sampling."""
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from fogsim.errors import InputError
from fogsim.input_validation import integer
from .templates import DagDiagnostic, DagTaskSpec, DagTemplate

DAX_NAMESPACE = "http://pegasus.isi.edu/schema/DAX"


def _tag(tag):
    if tag.startswith("{"):
        namespace, local = tag[1:].split("}", 1)
        return namespace, local.lower()
    return "", tag.lower()


def parse_dax(path, *, dag_type_id=None) -> DagTemplate:
    """Read once, hash those exact bytes, and return a complete immutable graph.

    A failure returns no partial template. Namespace prefixes and XML comments
    have no graph meaning. File attributes and uses metadata are not task data.
    """
    try:
        path = Path(path)
    except (TypeError, ValueError) as exc:
        raise InputError(f"DAX path must be a path string or Path: {path!r}") from exc
    if dag_type_id is not None:
        integer(dag_type_id, "dag_type_id", 0, 19)

    def fail(code, location, detail):
        raise InputError(f"{path}: {code} at {location}: {detail}")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        fail("DAX_READ_ERROR", "file", str(exc))
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        fail("DAX_XML_ERROR", "document", str(exc))
    namespace, local = _tag(root.tag)
    if local != "adag":
        fail("DAX_ROOT_ERROR", "root", f"expected adag, got {root.tag!r}")
    if namespace not in ("", DAX_NAMESPACE):
        fail("DAX_NAMESPACE_ERROR", "root", f"unsupported namespace {namespace!r}")

    def structure(node, location):
        ns, name = _tag(node.tag)
        if ns != namespace:
            fail("DAX_NAMESPACE_ERROR", location,
                 f"{node.tag!r} differs from root namespace; id={node.get('id')!r}, ref={node.get('ref')!r}")
        return name

    def reference(node, attribute, location):
        value = node.get(attribute)
        if value is None or not value.strip():
            fail("DAX_ID_ERROR", location, f"missing/blank {attribute}={value!r}")
        return value  # Preserve parsed spelling/whitespace; no trim or suffix conversion.

    tasks, edges = [], []
    seen_ids, seen_edges = set(), set()
    child_blocks = 0
    for index, node in enumerate(root, 1):
        location = f"root element {index} ({node.tag})"
        name = structure(node, location)
        if name == "job":
            tid = reference(node, "id", location)
            if tid in seen_ids:
                fail("DAX_DUPLICATE_ID", location, f"id={tid!r}")
            seen_ids.add(tid)
            tasks.append(DagTaskSpec(tid, len(tasks)))
        elif name == "child":
            child_blocks += 1
            child = reference(node, "ref", location)
            if child not in seen_ids:
                fail("DAX_UNKNOWN_OR_FORWARD_REFERENCE", location, f"child ref={child!r}")
            for parent_index, parent_node in enumerate(node, 1):
                parent_location = f"{location}, parent element {parent_index}"
                if structure(parent_node, parent_location) != "parent":
                    fail("DAX_UNSUPPORTED_STRUCTURE", parent_location, f"expected parent, got {parent_node.tag!r}")
                parent = reference(parent_node, "ref", parent_location)
                if len(parent_node):
                    fail("DAX_UNSUPPORTED_STRUCTURE", parent_location, f"nested parent ref={parent!r}")
                if parent not in seen_ids:
                    fail("DAX_UNKNOWN_OR_FORWARD_REFERENCE", parent_location, f"parent ref={parent!r}, child ref={child!r}")
                if parent == child:
                    fail("DAX_SELF_EDGE", parent_location, f"parent=child={parent!r}")
                edge = parent, child
                if edge in seen_edges:
                    fail("DAX_DUPLICATE_EDGE", parent_location, f"parent={parent!r}, child={child!r}")
                seen_edges.add(edge)
                edges.append(edge)
        else:
            fail("DAX_UNSUPPORTED_STRUCTURE", location, f"unsupported root child {node.tag!r}")
    if not tasks:
        fail("DAX_EMPTY_GRAPH", "root", "no job elements")
    diagnostics = []
    for attribute, actual in (("jobCount", len(tasks)), ("childCount", child_blocks)):
        declared = root.get(attribute)
        if declared is not None:
            valid = declared.isascii() and declared.isdecimal() and len(declared) <= 20
            if not valid or int(declared) != actual:
                diagnostics.append(DagDiagnostic(
                    "DECLARED_COUNT_MISMATCH" if valid else "DECLARED_COUNT_INVALID",
                    attribute, declared, actual))
    try:
        return DagTemplate(dag_type_id, path.name, hashlib.sha256(raw).hexdigest(),
                           tuple(tasks), tuple(edges), tuple(diagnostics))
    except InputError as exc:
        fail("DAX_TOPOLOGY_ERROR", "root (complete graph)", f"{exc}; related id/ref edges={edges!r}")
