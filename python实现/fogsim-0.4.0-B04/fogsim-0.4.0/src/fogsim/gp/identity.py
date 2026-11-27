"""Frozen CJ bytes and layered rule identities; no runtime state or RNG access."""
import hashlib
import json
from .ast import export_ast
from .diagnostics import GPCode, GPDiagnostic, GPInputError
from fogsim.rules.specs import (LANGUAGE_VERSION, FEATURE_SEMANTICS_VERSION,
    NUMERIC_SEMANTICS_VERSION, SELECTION_POLICY_VERSION, IDENTITY_ENCODING_VERSION,
    FCFS_SEMANTICS_VERSION, FIXED_RESOURCE_SEMANTICS_VERSION)


def _invalid(message, path="rule_manifest"):
    raise GPInputError(GPDiagnostic(GPCode.RULE_IDENTITY_MISMATCH, message, path))


def canonical_json(value):
    """CJ's restricted types, ASCII keys, surrogate validation, and DEL escape."""
    work = [value]
    while work:
        item = work.pop()
        if type(item) is dict:
            if any(type(k) is not str or not k.isascii() for k in item):
                raise ValueError("CJ keys must be ASCII strings")
            work.extend(item.keys()); work.extend(item.values())
        elif type(item) is list:
            work.extend(item)
        elif type(item) is str:
            i = 0
            while i < len(item):
                n = ord(item[i]); i += 1
                if 0xD800 <= n <= 0xDBFF:
                    if i == len(item) or not 0xDC00 <= ord(item[i]) <= 0xDFFF:
                        raise ValueError("unpaired surrogate")
                    i += 1
                elif 0xDC00 <= n <= 0xDFFF:
                    raise ValueError("unpaired surrogate")
        elif type(item) is not int or item < 0:
            raise ValueError("CJ accepts objects, arrays, strings and nonnegative integers")
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"), allow_nan=False).replace(chr(127), "\\u007f").encode("ascii")


def digest(domain, payload):
    return "sha256:" + hashlib.sha256(domain.encode("ascii") + b"\n" + canonical_json(payload)).hexdigest()


def source_sha256(text):
    try:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    except (AttributeError, UnicodeError) as exc:
        _invalid(f"invalid UTF-8 expression source: {exc}")


def expression_record(compiled):
    payload = dict(identity_encoding_version=IDENTITY_ENCODING_VERSION,
        language_version=compiled.language_version,
        feature_semantics_version=compiled.feature_semantics_version,
        numeric_semantics_version=compiled.numeric_semantics_version, ast=export_ast(compiled.root))
    return dict(payload, expression_id=digest("fogsim.expression-id.v1", payload))


def binding_record(spec, compiled=None):
    payload = dict(identity_encoding_version=IDENTITY_ENCODING_VERSION,
        role=spec.role.value, kind=spec.kind, selection_policy_version=SELECTION_POLICY_VERSION)
    if spec.kind == "gp":
        payload["expression_id"] = expression_record(compiled)["expression_id"]
    else:
        payload["baseline_semantics_version"] = (FCFS_SEMANTICS_VERSION if spec.kind == "fcfs"
                                                 else FIXED_RESOURCE_SEMANTICS_VERSION)
        if spec.kind == "fixed_resource": payload["resource_id"] = spec.resource_id
    record = dict(payload, rule_id=digest("fogsim.rule-id.v1", payload))
    if spec.kind == "gp":
        # The encoding version is global; the GP binding has the exact 5.6 shape.
        del record["identity_encoding_version"]
        record["source"] = dict(expression=spec.expression, source_sha256=source_sha256(spec.expression))
    return record


def rule_manifest(prepared):
    expressions, bindings = {}, {}
    for role in ("routing", "sequencing"):
        spec, rule = getattr(prepared, role + "_spec"), getattr(prepared, role)
        program = rule.compiled if spec.kind == "gp" else None
        if program is not None:
            record = expression_record(program)
            expressions[record["expression_id"]] = record
        bindings[role] = binding_record(spec, program)
    pair = dict(identity_encoding_version=IDENTITY_ENCODING_VERSION,
        routing_rule_id=bindings["routing"]["rule_id"], sequencing_rule_id=bindings["sequencing"]["rule_id"])
    return dict(identity_encoding_version=IDENTITY_ENCODING_VERSION,
        expressions=[expressions[k] for k in sorted(expressions)], bindings=bindings,
        rule_pair_id=digest("fogsim.rule-pair-id.v1", pair))


def validate_rule_manifest(value, *, prepared_rules=None):
    """Reparse source, compare the ordered AST and all identities; never trust AST code."""
    from fogsim.rules.specs import RuleSpec
    from fogsim.rules.factory import prepare_rules
    try:
        if type(value) is not dict or set(value) != {"identity_encoding_version", "expressions", "bindings", "rule_pair_id"}:
            _invalid("invalid manifest fields")
        if value["identity_encoding_version"] != IDENTITY_ENCODING_VERSION:
            _invalid("unsupported identity version")
        if type(value["expressions"]) is not list:
            _invalid("expressions must be an array")
        for ex in value["expressions"]:
            if type(ex) is not dict or set(ex) != {"identity_encoding_version", "language_version",
                    "feature_semantics_version", "numeric_semantics_version", "ast", "expression_id"}:
                _invalid("invalid expression fields")
            for key, version in (("identity_encoding_version", IDENTITY_ENCODING_VERSION),
                ("language_version", LANGUAGE_VERSION), ("feature_semantics_version", FEATURE_SEMANTICS_VERSION),
                ("numeric_semantics_version", NUMERIC_SEMANTICS_VERSION)):
                if ex[key] != version: _invalid("unsupported " + key)
        if type(value["bindings"]) is not dict or set(value["bindings"]) != {"routing", "sequencing"}:
            _invalid("two explicit role bindings required")
        specs = []
        for role in ("routing", "sequencing"):
            binding = value["bindings"][role]
            if type(binding) is not dict or binding.get("role") != role: _invalid("binding role mismatch")
            kind = binding["kind"]
            if kind == "gp":
                source = binding["source"]
                if type(source) is not dict or set(source) != {"expression", "source_sha256"}: _invalid("invalid source fields")
                specs.append(RuleSpec(role, kind, expression=source["expression"]))
            else:
                specs.append(RuleSpec(role, kind, resource_id=binding.get("resource_id")))
        prepared = prepare_rules(*specs)
        if canonical_json(value) != canonical_json(rule_manifest(prepared)):
            _invalid("source, AST, versions or derived identities mismatch")
        if prepared_rules is not None and canonical_json(value) != canonical_json(rule_manifest(prepared_rules)):
            _invalid("manifest does not match active configuration/source")
        return prepared
    except GPInputError as exc:
        if exc.code == GPCode.RULE_IDENTITY_MISMATCH.value: raise
        raise GPInputError(GPDiagnostic(GPCode.RULE_IDENTITY_MISMATCH, str(exc), "rule_manifest")) from exc
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError) as exc:
        raise GPInputError(GPDiagnostic(GPCode.RULE_IDENTITY_MISMATCH, str(exc), "rule_manifest")) from exc
