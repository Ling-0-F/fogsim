"""Per-call local stack execution; no model writes, feature cache or RNG."""
import struct

from .features import read_feature
from .numerics import apply_binary
from .program import CompiledExpression, Opcode


def evaluate(compiled: CompiledExpression, option, context, *, observer=None) -> float:
    if type(compiled) is not CompiledExpression:
        raise TypeError("evaluate requires a CompiledExpression")
    # Optional acceptance observer receives immutable instruction/scalar only.
    # It runs at the actual leaf read, never by evaluating the expression again.
    values = []
    for instruction in compiled.instructions:
        if instruction.opcode == Opcode.PUSH_CONST:
            values.append(struct.unpack(">d", bytes.fromhex(instruction.operand))[0])
        elif instruction.opcode == Opcode.READ_FEATURE:
            values.append(read_feature(instruction.operand, option, context))
        elif instruction.opcode == Opcode.APPLY_BINARY:
            b = values.pop()
            a = values.pop()
            values.append(apply_binary(instruction.operand, a, b))
        else:
            raise RuntimeError("unknown instruction in compiled GP expression")
        if observer is not None and instruction.opcode != Opcode.APPLY_BINARY:
            observer(instruction, values[-1])
    if len(values) != 1:
        raise RuntimeError("compiled GP expression has invalid final stack")
    return values[0]
