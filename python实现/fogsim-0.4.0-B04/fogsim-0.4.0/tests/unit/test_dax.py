"""V02/V03 Python topology checks; Java execution has its own explicit tool."""
from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path
import random
import pytest
from conftest import ROOT
from fogsim import parse_dax, load_dax_catalog, load_experiment_config, prepare_random_input
from fogsim.errors import InputError
from fogsim.experiment_config import WorkflowTypeRange
from fogsim.instances.catalog import STANDARD_DAX_FILES


COUNTS = (30, 24, 30, 25, 29, 50, 47, 50, 50, 58, 100, 100, 100, 100, 97, 1000, 997, 1000, 1000, 968)
EDGES = (52, 27, 35, 45, 33, 88, 54, 60, 106, 66, 180, 122, 119, 233, 109, 1988, 1234, 1233, 2485, 1096)


def write(tmp_path, content):
    path = tmp_path / "case.xml"
    path.write_text(content, encoding="utf-8")
    return path


def config(dag_root=ROOT / "dax", lower=0, upper=19, seed=0):
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    return replace(cfg, source=replace(cfg.source, dag_root=dag_root, seed=seed,
                                      workflow_types=WorkflowTypeRange(lower, upper)))


@pytest.mark.parametrize("type_id", range(20))
def test_all_standard_files(type_id):
    path = ROOT / "dax" / STANDARD_DAX_FILES[type_id]
    t = parse_dax(path, dag_type_id=type_id)
    assert len(t.tasks) == COUNTS[type_id] and len(t.dependencies) == EDGES[type_id]
    assert t.ref.dag_type_id == type_id
    assert t.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert tuple(task.java_index for task in t.tasks) == tuple(range(len(t.tasks)))
    assert not t.diagnostics


@pytest.mark.parametrize("opening,prefix", [
    ("<adag>", ""),
    ('<adag xmlns="http://pegasus.isi.edu/schema/DAX">', ""),
    ('<d:ADAG xmlns:d="http://pegasus.isi.edu/schema/DAX" xmlns:x="http://pegasus.isi.edu/schema/DAX">', "x:"),
])
def test_namespace_case_and_adjacency_order(tmp_path, opening, prefix):
    closing = "</d:ADAG>" if opening.startswith("<d:") else "</adag>"
    body = ('<!-- comments do not count as structure -->'
            '<{p}JOB id="Z"/><{p}job id="A"/><{p}job id=" node-01 "/>'
            '<{p}child ref=" node-01 "><{p}parent ref="A"/><{p}parent ref="Z"/></{p}child>'
            '<{p}child ref="A"><{p}parent ref="Z"/></{p}child>').format(p=prefix)
    t = parse_dax(write(tmp_path, opening + body + closing))
    assert t.task_mapping == (("Z", 0), ("A", 1), (" node-01 ", 2))
    assert t.dependencies == (("A", " node-01 "), ("Z", " node-01 "), ("Z", "A"))
    parents, children = t.adjacency()
    assert parents[" node-01 "] == ("A", "Z")
    assert children["Z"] == (" node-01 ", "A")
    parents.clear()
    assert t.adjacency()[0][" node-01 "] == ("A", "Z")


@pytest.mark.parametrize("body,code", [
    ('', "DAX_EMPTY_GRAPH"),
    ('<job/>', "DAX_ID_ERROR"), ('<job id=" "/>', "DAX_ID_ERROR"),
    ('<job id="x"/><job id="x"/>', "DAX_DUPLICATE_ID"),
    ('<job id="x"/><child/>', "DAX_ID_ERROR"),
    ('<job id="x"/><child ref="x"><parent/></child>', "DAX_ID_ERROR"),
    ('<job id="x"/><child ref="y"/>', "DAX_UNKNOWN_OR_FORWARD_REFERENCE"),
    ('<child ref="x"/><job id="x"/>', "DAX_UNKNOWN_OR_FORWARD_REFERENCE"),
    ('<job id="x"/><child ref="x"><parent ref="y"/></child><job id="y"/>', "DAX_UNKNOWN_OR_FORWARD_REFERENCE"),
    ('<job id="x"/><child ref="x"><parent ref="x"/></child>', "DAX_SELF_EDGE"),
    ('<job id="x"/><job id="y"/><child ref="y"><parent ref="x"/><parent ref="x"/></child>', "DAX_DUPLICATE_EDGE"),
    ('<job id="x"/><job id="y"/><child ref="y"><parent ref="x"/></child><child ref="y"><parent ref="x"/></child>', "DAX_DUPLICATE_EDGE"),
    ('<job id="x"/><job id="y"/><child ref="y"><parent ref="x"/></child><child ref="x"><parent ref="y"/></child>', "DAX_TOPOLOGY_ERROR"),
    ('<job id="x"/><file/>', "DAX_UNSUPPORTED_STRUCTURE"),
    ('<job id="x"/><child ref="x"><other/></child>', "DAX_UNSUPPORTED_STRUCTURE"),
    ('<job id="x"/><job id="y"/><child ref="y"><parent ref="x"><uses/></parent></child>', "DAX_UNSUPPORTED_STRUCTURE"),
])
def test_invalid_graph_is_complete_failure(tmp_path, body, code):
    path = write(tmp_path, "<adag>" + body + "</adag>")
    with pytest.raises(InputError, match=code) as error:
        parse_dax(path)
    assert str(path) in str(error.value) and " at " in str(error.value)


@pytest.mark.parametrize("xml,code", [
    ('<wrong/>', "DAX_ROOT_ERROR"), ('<adag xmlns="urn:unknown"/>', "DAX_NAMESPACE_ERROR"),
    ('<adag xmlns="http://pegasus.isi.edu/schema/DAX"><job xmlns="" id="x"/></adag>', "DAX_NAMESPACE_ERROR"),
    ('<adag><job id="x"/><d:child xmlns:d="http://pegasus.isi.edu/schema/DAX" ref="x"/></adag>', "DAX_NAMESPACE_ERROR"),
    ('<adag><job id="x"/><job id="y"/><child ref="y"><p:parent xmlns:p="urn:other" ref="x"/></child></adag>', "DAX_NAMESPACE_ERROR"),
    ('<adag><job id="x"></adag>', "DAX_XML_ERROR"),
    ('<adag><job id="x" id="y"/></adag>', "DAX_XML_ERROR"),
    ('<adag><job id="&external;"/></adag>', "DAX_XML_ERROR"),
])
def test_document_errors(tmp_path, xml, code):
    with pytest.raises(InputError, match=code): parse_dax(write(tmp_path, xml))


def test_encoding_ids_ignored_metadata_and_nonconnected_graph(tmp_path):
    path = tmp_path / "encoded.xml"
    raw = ('<?xml version="1.0" encoding="UTF-16"?>'
           '<adag xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://invalid.example/no-fetch">'
           '<job id="中文 &amp; 原 ID" runtime="NaN"><uses file="f" size="-999"/></job>'
           '<job id="中文 &amp; 原 id"/><job id="orphan"/></adag>').encode("utf-16")
    path.write_bytes(raw)
    t = parse_dax(path)
    assert tuple(task.xml_id for task in t.tasks) == ("中文 & 原 ID", "中文 & 原 id", "orphan")
    assert not t.dependencies
    assert t.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_count_diagnostics_are_immutable_and_nonfatal(tmp_path):
    t = parse_dax(ROOT / "dax/HEFT_paper.xml")
    assert t.dag_type_id is None and len(t.tasks) == 10
    assert [(d.attribute, d.declared_value, d.actual_count) for d in t.diagnostics] == [
        ("jobCount", "25", 10), ("childCount", "20", 9)]
    with pytest.raises(FrozenInstanceError): t.diagnostics[0].actual_count = 99
    bad = parse_dax(write(tmp_path, '<adag jobCount="n/a" childCount="-1"><job id="x"/></adag>'))
    assert [d.code for d in bad.diagnostics] == ["DECLARED_COUNT_INVALID", "DECLARED_COUNT_INVALID"]
    # childCount counts child blocks, not edges.
    multi = parse_dax(write(tmp_path, '<adag childCount="1"><job id="a"/><job id="b"/><job id="c"/>'
        '<child ref="c"><parent ref="a"/><parent ref="b"/></child></adag>'))
    assert len(multi.dependencies) == 2 and not multi.diagnostics
    assert parse_dax(ROOT / "dax/floodplain.xml").dag_type_id is None


def test_catalog_selected_range_frozen_after_file_changes(tmp_path, monkeypatch):
    for name in STANDARD_DAX_FILES[:2]:
        (tmp_path / name).write_bytes((ROOT / "dax" / name).read_bytes())
    cfg = config(tmp_path, 0, 1)
    monkeypatch.chdir(tmp_path.parent)
    catalog = load_dax_catalog(cfg)
    assert tuple(t.dag_type_id for t in catalog.templates) == (0, 1)
    old = catalog.template(1)
    (tmp_path / STANDARD_DAX_FILES[1]).write_text('<adag><job id="new"/></adag>')
    assert catalog.template(1) is old and len(old.tasks) == 24
    assert load_dax_catalog(cfg).template(1).source_sha256 != old.source_sha256
    with pytest.raises(InputError): catalog.template(2)
    with pytest.raises(InputError): catalog.template(True)
    with pytest.raises(FrozenInstanceError): catalog.templates = ()


def test_catalog_failure_and_loading_never_construct_or_draw_rng(tmp_path, monkeypatch):
    state = random.getstate()
    def forbidden(*args, **kwargs): raise AssertionError("catalog cannot construct/draw RNG")
    monkeypatch.setattr(random, "Random", forbidden)
    monkeypatch.setattr(random, "random", forbidden)
    assert len(load_dax_catalog(config(ROOT / "dax", 4, 4)).templates) == 1
    # First file succeeds; second fails. Preparation must not construct an RNG.
    (tmp_path / STANDARD_DAX_FILES[0]).write_bytes((ROOT / "dax" / STANDARD_DAX_FILES[0]).read_bytes())
    with pytest.raises(InputError, match="DAX_READ_ERROR"): prepare_random_input(config(tmp_path, 0, 1))
    assert random.getstate() == state


def test_invalid_path_type_and_config(tmp_path):
    with pytest.raises(InputError, match="DAX_READ_ERROR"): parse_dax(tmp_path / "missing.xml")
    for bad in (True, -1, 20, 1.0):
        with pytest.raises(InputError): parse_dax(ROOT / "dax/HEFT_paper.xml", dag_type_id=bad)
    with pytest.raises(InputError): load_dax_catalog({})
    for path in (None, True, 1):
        with pytest.raises(InputError, match="DAX path"): parse_dax(path)
