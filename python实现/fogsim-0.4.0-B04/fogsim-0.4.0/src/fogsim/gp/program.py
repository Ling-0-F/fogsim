"""Iterative, left-before-right postorder compilation with a static stack bound."""
from dataclasses import dataclass, field
from enum import Enum

from fogsim.rules.specs import LANGUAGE_VERSION, FEATURE_SEMANTICS_VERSION, NUMERIC_SEMANTICS_VERSION
from .ast import ConstantNode, Node, ParsedExpression, structural_key
from .features import Feature
from .numerics import BinaryFunction


class Opcode(str, Enum):
    PUSH_CONST = "PUSH_CONST"
    READ_FEATURE = "READ_FEATURE"
    APPLY_BINARY = "APPLY_BINARY"


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: Opcode
    operand: str | Feature | BinaryFunction
    node_index: int

    def __post_init__(self):
        object.__setattr__(self, "opcode", Opcode(self.opcode))
        if type(self.node_index) is not int or self.node_index < 0:
            raise ValueError("node index must be a nonnegative integer")
        if self.opcode == Opcode.PUSH_CONST:
            ConstantNode(self.operand)
        elif self.opcode == Opcode.READ_FEATURE:
            object.__setattr__(self, "operand", Feature(self.operand))
        else:
            object.__setattr__(self, "operand", BinaryFunction(self.operand))


def validate_instructions(instructions: tuple[Instruction, ...]) -> int:
    """Reject empty/invalid programs, underflow and a final stack other than one."""
    if type(instructions) is not tuple:
        raise TypeError("instructions must be an immutable tuple")
    depth = maximum = 0
    for instruction in instructions:
        if type(instruction) is not Instruction:
            raise TypeError("invalid GP instruction")
        if instruction.opcode in (Opcode.PUSH_CONST, Opcode.READ_FEATURE):
            depth += 1
            maximum = max(maximum, depth)
        elif instruction.opcode == Opcode.APPLY_BINARY:
            if depth < 2:
                raise ValueError("GP instruction stack underflow")
            depth -= 1
        else:
            raise ValueError("unknown GP instruction")
    if depth != 1:
        raise ValueError("GP instruction stack must finish with exactly one value")
    return maximum


@dataclass(frozen=True, slots=True)
class CompiledExpression:
    root: Node
    instructions: tuple[Instruction, ...] = field(init=False)
    max_stack: int = field(init=False)
    structure_key: tuple[tuple, ...] = field(init=False)
    language_version: str = field(default=LANGUAGE_VERSION, init=False)
    feature_semantics_version: str = field(default=FEATURE_SEMANTICS_VERSION, init=False)
    numeric_semantics_version: str = field(default=NUMERIC_SEMANTICS_VERSION, init=False)

    def __post_init__(self):
        structure = structural_key(self.root)
        work = [(0, False)]
        instructions = []
        while work:
            index, expanded = work.pop()
            record = structure[index]
            if record[0] == "binary" and not expanded:
                work.append((index, True))
                work.append((record[3], False))
                work.append((record[2], False))
                continue
            opcode = {"constant": Opcode.PUSH_CONST, "feature": Opcode.READ_FEATURE,
                      "binary": Opcode.APPLY_BINARY}[record[0]]
            instructions.append(Instruction(opcode, record[1], index))
        immutable = tuple(instructions)
        object.__setattr__(self, "instructions", immutable)
        object.__setattr__(self, "max_stack", validate_instructions(immutable))
        object.__setattr__(self, "structure_key", structure)

    @property
    def expression_id(self):
        from .identity import expression_record
        return expression_record(self)["expression_id"]


def compile_expression(parsed: ParsedExpression) -> CompiledExpression:
    if type(parsed) is not ParsedExpression:
        raise TypeError("compile_expression requires a ParsedExpression")
    return CompiledExpression(parsed.root)
