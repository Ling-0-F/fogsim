from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
import pytest
from fogsim.gp.identity import canonical_json, digest, rule_manifest, validate_rule_manifest
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression
from fogsim.gp.diagnostics import GPInputError
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec


def pair(a="(+ PT 1)", b="(+ PT 1.0)"):
    return prepare_rules(RuleSpec("routing", "gp", expression=a), RuleSpec("sequencing", "gp", expression=b))


@pytest.mark.parametrize("value, expected", [
    ({"z":0,"a":[12,"/",'"',"\\"]}, b'{"a":[12,"/","\\\"","\\\\"],"z":0}'),
    (["\b\f\n\r\t\x00\x1f\x7f"], b'["\\b\\f\\n\\r\\t\\u0000\\u001f\\u007f"]'),
    (["雾🚀"], b'["\\u96fe\\ud83d\\ude80"]'),
    (["é","e\u0301"], b'["\\u00e9","e\\u0301"]'),
    (["\ud83d\ude80"], b'["\\ud83d\\ude80"]'),
])
def test_exact_cj_bytes_and_domain(value, expected, evidence_b04):
    assert canonical_json(value) == expected
    assert digest("fogsim.rule-id.v1", value) == "sha256:"+hashlib.sha256(b"fogsim.rule-id.v1\n"+expected).hexdigest()
    evidence_b04("cj", dict(input=value, cj=expected.decode(), digest=digest("fogsim.rule-id.v1", value)))


@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, (), {1:"x"}, {"é":0}, "\ud800", "\udc00", "\ud800x"])
def test_cj_rejects_outside_payload(value):
    with pytest.raises(ValueError): canonical_json(value)


@pytest.mark.parametrize("a,b,equal", [("1","1.0",True),("1d","1F",True),
    ("(+ PT 1)","( +\tPT\r\n1.0 )",True),("-0.0","0.0",False),
    ("(+ PT UT)","(+ UT PT)",False),("(+ (+ PT UT) DT)","(+ PT (+ UT DT))",False)])
def test_identity_source_structure_role_layers(a,b,equal,evidence_b04):
    p=pair(a,b); m=p.rule_manifest
    r,s=m["bindings"].values()
    assert (r["expression_id"]==s["expression_id"]) is equal
    assert r["rule_id"] != s["rule_id"]
    assert r["source"]["source_sha256"] != s["source"]["source_sha256"]
    assert len(m["expressions"]) == (1 if equal else 2)
    assert m["expressions"]==sorted(m["expressions"],key=lambda v:v["expression_id"])
    assert validate_rule_manifest(m).rule_manifest==m
    assert p.rule_pair_id==m["rule_pair_id"]
    evidence_b04("identity",m)


@pytest.mark.parametrize("route", [RuleSpec("routing"),RuleSpec("routing","fixed_resource","雾/\"\\🚀")])
def test_baseline_unicode_and_versions(route,evidence_b04):
    p=prepare_rules(route,RuleSpec("sequencing")); m=p.rule_manifest
    assert not m["expressions"]
    assert "source" not in m["bindings"]["routing"]
    assert validate_rule_manifest(m).rule_pair_id==p.rule_pair_id
    detached=p.rule_manifest;detached["bindings"]["routing"]["kind"]="gp"
    assert p.rule_manifest==m
    evidence_b04("baseline-identity",m)


MUTATIONS=[
 lambda m:m.update(extra=0),lambda m:m.update(identity_encoding_version="unknown"),
 lambda m:m.update(rule_pair_id="sha256:"+"0"*64),
 lambda m:m["bindings"].pop("sequencing"),
 lambda m:m["bindings"]["routing"].update(role="sequencing"),
 lambda m:m["bindings"]["routing"].update(rule_id="bad"),
 lambda m:m["bindings"]["routing"]["source"].update(expression="(+ PT 2)"),
 lambda m:m["bindings"]["routing"]["source"].update(source_sha256="bad"),
 lambda m:m["bindings"]["routing"]["source"].update(extra=0),
 lambda m:m["expressions"][0].update(language_version="unknown"),
 lambda m:m["expressions"][0].update(feature_semantics_version="unknown"),
 lambda m:m["expressions"][0].update(numeric_semantics_version="unknown"),
 lambda m:m["expressions"][0].update(expression_id="bad"),
 lambda m:m["expressions"][0]["ast"].update(root=True),
 lambda m:m["expressions"][0]["ast"]["nodes"][0].update(left=0),
 lambda m:m["expressions"][0]["ast"]["nodes"][0].update(right=1),
 lambda m:m["expressions"][0]["ast"]["nodes"].append({"kind":"feature","name":"PT"}),
 lambda m:m["expressions"].append(deepcopy(m["expressions"][0])),
 lambda m:m["expressions"][0]["ast"]["nodes"][2].update(bits="0000000000000000"),
]
@pytest.mark.parametrize("mutation",MUTATIONS)
def test_manifest_tamper_rejected_without_repair(mutation):
    m=pair().rule_manifest;mutation(m);before=deepcopy(m)
    with pytest.raises(GPInputError,match="GP_RULE_IDENTITY_MISMATCH"):validate_rule_manifest(m)
    assert m==before


def test_active_source_binding_must_match():
    m=pair().rule_manifest
    with pytest.raises(GPInputError):validate_rule_manifest(m,prepared_rules=pair("(+ PT 1.0)"))


@pytest.mark.parametrize("left",[True,False])
def test_deep_2500_manifest_roundtrip(left,evidence_b04):
    text="PT"
    for _ in range(2500): text="(+ "+text+" 1)" if left else "(+ 1 "+text+")"
    p=pair(text,text); m=p.rule_manifest
    assert len(m["expressions"][0]["ast"]["nodes"])==5001
    assert json.loads(json.dumps(m))==m
    assert validate_rule_manifest(m).rule_pair_id==p.rule_pair_id
    evidence_b04("deep-identity", dict(left=left,rule_pair_id=p.rule_pair_id,nodes=5001))
