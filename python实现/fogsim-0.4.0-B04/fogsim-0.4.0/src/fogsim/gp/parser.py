"""Strict fixed-GP Lisp lexer/parser, using explicit frames throughout."""
from dataclasses import dataclass, field
import re
import string

from .ast import BinaryNode, ConstantNode, FeatureNode, ParsedExpression, SourceSpan
from .diagnostics import GPCode, GPDiagnostic, GPInputError
from .features import Feature
from .numerics import BinaryFunction

ASCII_WHITESPACE = " \t\n\v\f\r"
# Underscores are scanned as part of a token so numeric intent (1_0) receives
# INVALID_CONSTANT. They never become valid features, functions or numbers.
_TOKEN_CHARACTERS = frozenset(string.ascii_letters + string.digits + "+-*/._")
_NUMBER = re.compile(r"-?(?:0[0-7]+|(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[dDfF]?)", re.ASCII)


@dataclass(frozen=True, slots=True)
class _Token:
    text: str
    start: int
    end: int


@dataclass(slots=True)
class _Frame:
    start: int
    source_index: int
    function: BinaryFunction | None = None
    children: list = field(default_factory=list)


def parse_expression(text: str, *, role=None, field_path="expression") -> ParsedExpression:
    """Parse one entire expression; optional metadata only decorates errors.

    Lexical rejection precedes all structural diagnosis. A completed root's
    following token is TRAILING_INPUT, including an extra closing parenthesis.
    EOF in an open call is UNBALANCED before that call's missing operands.
    """
    if type(text) is not str:
        raise TypeError("GP expression must be a string")
    if role not in (None, "routing", "sequencing") or type(field_path) is not str:
        raise ValueError("invalid parser diagnostic metadata")

    def fail(code, message, start, end):
        raise GPInputError(GPDiagnostic.at_source(code, message, text=text,
            start=start, end=end, role=role, field_path=field_path))

    for index, character in enumerate(text):
        if character not in _TOKEN_CHARACTERS and character not in ASCII_WHITESPACE + "()":
            fail(GPCode.INVALID_CHARACTER, "character is not permitted in the GP language", index, index + 1)
    tokens = []
    index = 0
    while index < len(text):
        if text[index] in ASCII_WHITESPACE:
            index += 1
            continue
        start = index
        if text[index] in "()":
            index += 1
        else:
            while index < len(text) and text[index] not in ASCII_WHITESPACE + "()":
                index += 1
        tokens.append(_Token(text[start:index], start, index))
    if not tokens:
        fail(GPCode.EMPTY_EXPRESSION, "expression is empty", len(text), len(text))

    frames = []
    spans = []
    root = None

    def attach(node):
        nonlocal root
        if frames:
            frames[-1].children.append(node)
        else:
            root = node

    for token in tokens:
        if root is not None and not frames:
            fail(GPCode.TRAILING_INPUT, "expected the end of the expression", token.start, token.end)
        if frames and frames[-1].function is None:
            try:
                frames[-1].function = BinaryFunction(token.text)
            except ValueError:
                fail(GPCode.UNKNOWN_FUNCTION, "expected one of the six binary functions", token.start, token.end)
            continue
        if token.text == ")":
            if not frames:
                fail(GPCode.UNBALANCED_PARENTHESES, "closing parenthesis has no open call", token.start, token.end)
            frame = frames.pop()
            if len(frame.children) != 2:
                fail(GPCode.ARITY_ERROR, "a function requires exactly two expressions", token.start, token.end)
            spans[frame.source_index] = SourceSpan(frame.start, token.end)
            attach(BinaryNode(frame.function, *frame.children))
            continue
        if frames and len(frames[-1].children) == 2:
            fail(GPCode.ARITY_ERROR, "a function has more than two expressions", token.start, token.end)
        if token.text == "(":
            frames.append(_Frame(token.start, len(spans)))
            spans.append(None)
            continue
        if _NUMBER.fullmatch(token.text):
            number = token.text[:-1] if token.text[-1] in "dDfF" else token.text
            try:
                value = float(number)
            except (ValueError, OverflowError) as exc:
                diagnostic = GPDiagnostic.at_source(GPCode.INVALID_CONSTANT, "invalid binary64 constant",
                    text=text, start=token.start, end=token.end, role=role, field_path=field_path)
                raise GPInputError(diagnostic) from exc
            node = ConstantNode.from_float(value)
        else:
            if token.text[0] in "+-.0123456789":
                fail(GPCode.INVALID_CONSTANT, "constant does not match the frozen number grammar", token.start, token.end)
            try:
                node = FeatureNode(Feature(token.text))
            except ValueError:
                fail(GPCode.UNKNOWN_FEATURE, "expected one of the ten features or a valid constant", token.start, token.end)
        spans.append(SourceSpan(token.start, token.end))
        attach(node)
    if frames:
        fail(GPCode.UNBALANCED_PARENTHESES, "end of input in an unclosed call", len(text), len(text))
    return ParsedExpression(text, root, tuple(spans))
