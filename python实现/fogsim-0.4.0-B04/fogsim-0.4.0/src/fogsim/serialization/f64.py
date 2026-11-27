"""Lossless, strict binary64 score tags, including raw NaN payloads."""
import re
import struct
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError


def _invalid(path):
    raise GPInputError(GPDiagnostic(GPCode.F64_ENCODING_INVALID,
        'expected exactly kind=f64 and sixteen lowercase hex bits', path))


def encode_f64(value, *, field_path="priority"):
    if type(value) is not float: _invalid(field_path)
    return dict(kind="f64", bits=struct.pack(">d", value).hex())


def decode_f64(value, *, field_path="priority"):
    if (type(value) is not dict or set(value) != {"kind", "bits"} or value["kind"] != "f64"
            or type(value["bits"]) is not str or re.fullmatch(r"[0-9a-f]{16}", value["bits"]) is None):
        _invalid(field_path)
    return struct.unpack(">d", bytes.fromhex(value["bits"]))[0]
