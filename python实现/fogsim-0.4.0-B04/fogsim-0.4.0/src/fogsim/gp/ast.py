"""Deeply immutable ordered trees and iterative, occurrence-based export.

Source text belongs to ParsedExpression, never to reusable semantic nodes.
The flat structural key is an exact local key, not the B04 expression_id.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import struct

from .features import Feature
from .numerics import BinaryFunction

_BITS = re.compile(r"[0-9a-f]{16}", re.ASCII)


class _Node:
    __slots__ = ()

    def __eq__(self, other):
        if not isinstance(other, _Node):
            return NotImplemented
        return structural_key(self) == structural_key(other)

    def __hash__(self):
        return hash(structural_key(self))

    def __repr__(self):
        if type(self) is FeatureNode:
            return f"FeatureNode({self.feature.value!r})"
        if type(self) is ConstantNode:
            return f"ConstantNode({self.bits!r})"
        return f"BinaryNode({self.function.value!r}, occurrences={len(structural_key(self))})"


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class FeatureNode(_Node):
    feature: Feature

    def __post_init__(self):
        object.__setattr__(self, "feature", Feature(self.feature))


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class ConstantNode(_Node):
    bits: str

    def __post_init__(self):
        if type(self.bits) is not str or _BITS.fullmatch(self.bits) is None:
            raise ValueError("constant bits must be sixteen lowercase hexadecimal digits")

    @property
    def value(self) -> float:
        return struct.unpack(">d", bytes.fromhex(self.bits))[0]

    @classmethod
    def from_float(cls, value: float):
        if type(value) is not float:
            raise TypeError("constant value must be a binary64 float")
        return cls(struct.pack(">d", value).hex())


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class BinaryNode(_Node):
    function: BinaryFunction
    left: Node
    right: Node

    def __post_init__(self):
        object.__setattr__(self, "function", BinaryFunction(self.function))
        _require_node(self.left)
        _require_node(self.right)


Node = FeatureNode | ConstantNode | BinaryNode


def _require_node(node):
    if type(node) not in (FeatureNode, ConstantNode, BinaryNode):
        raise TypeError("expected a FeatureNode, ConstantNode or BinaryNode")


def structural_key(root: Node) -> tuple[tuple, ...]:
    """Preorder, left before right; expand each shared-node occurrence.

    Ancestor detection rejects a corrupted cyclic tree without treating legal
    repeated references to an immutable subtree as a DAG in exported data.
    """
    records = []
    active = set()
    work = [(root, None, None, False)]
    while work:
        node, parent, side, leaving = work.pop()
        if leaving:
            active.remove(id(node))
            continue
        _require_node(node)
        if id(node) in active:
            raise ValueError("cyclic GP tree")
        index = len(records)
        if parent is not None:
            records[parent][side] = index
        if type(node) is FeatureNode:
            if type(node.feature) is not Feature:
                raise TypeError("invalid feature node")
            records.append(["feature", node.feature.value])
        elif type(node) is ConstantNode:
            if type(node.bits) is not str or _BITS.fullmatch(node.bits) is None:
                raise ValueError("invalid constant node")
            records.append(["constant", node.bits])
        else:
            if type(node.function) is not BinaryFunction:
                raise TypeError("invalid binary node")
            records.append(["binary", node.function.value, None, None])
            active.add(id(node))
            work.append((node, None, None, True))
            work.append((node.right, index, 3, False))
            work.append((node.left, index, 2, False))
    return tuple(tuple(record) for record in records)


def export_ast(root: Node) -> dict:
    """Return a fresh flat JSON-compatible tree with the frozen field shapes."""
    nodes = []
    for record in structural_key(root):
        if record[0] == "feature":
            nodes.append(dict(kind="feature", name=record[1]))
        elif record[0] == "constant":
            nodes.append(dict(kind="constant", bits=record[1]))
        else:
            nodes.append(dict(kind="binary", op=record[1], left=record[2], right=record[3]))
    return dict(root=0, nodes=nodes)


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int

    def __post_init__(self):
        if type(self.start) is not int or type(self.end) is not int or not 0 <= self.start <= self.end:
            raise ValueError("invalid source span")


@dataclass(frozen=True, slots=True)
class ParsedExpression:
    text: str
    root: Node
    spans: tuple[SourceSpan, ...]

    def __post_init__(self):
        if type(self.text) is not str or type(self.spans) is not tuple:
            raise TypeError("parsed expression requires original text and immutable spans")
        if any(type(span) is not SourceSpan or span.end > len(self.text) for span in self.spans):
            raise ValueError("source spans must belong to the original expression")
        if len(self.spans) != len(structural_key(self.root)):
            raise ValueError("one source span is required for each preorder occurrence")

    def export_ast(self):
        return export_ast(self.root)
