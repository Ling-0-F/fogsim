"""Immutable GP diagnostics, independent of the engine and input sources."""
from dataclasses import asdict, dataclass
from enum import Enum

from fogsim.errors import InputError, StateError


class GPCode(str, Enum):
    EMPTY_EXPRESSION = "GP_EMPTY_EXPRESSION"
    INVALID_CHARACTER = "GP_INVALID_CHARACTER"
    UNKNOWN_FUNCTION = "GP_UNKNOWN_FUNCTION"
    UNKNOWN_FEATURE = "GP_UNKNOWN_FEATURE"
    INVALID_CONSTANT = "GP_INVALID_CONSTANT"
    ARITY_ERROR = "GP_ARITY_ERROR"
    UNBALANCED_PARENTHESES = "GP_UNBALANCED_PARENTHESES"
    TRAILING_INPUT = "GP_TRAILING_INPUT"
    RULE_SPEC_INVALID = "GP_RULE_SPEC_INVALID"
    RULE_ROLE_MISMATCH = "GP_RULE_ROLE_MISMATCH"
    PREPARED_RULE_MISMATCH = "GP_PREPARED_RULE_MISMATCH"
    RULE_IDENTITY_MISMATCH = "GP_RULE_IDENTITY_MISMATCH"
    F64_ENCODING_INVALID = "GP_F64_ENCODING_INVALID"
    CONTEXT_IDENTITY_MISMATCH = "GP_CONTEXT_IDENTITY_MISMATCH"
    CONTEXT_PHASE_INVALID = "GP_CONTEXT_PHASE_INVALID"
    STATE_MUTATION_DETECTED = "GP_STATE_MUTATION_DETECTED"


@dataclass(frozen=True, slots=True)
class GPDiagnostic:
    code: GPCode
    message: str
    field_path: str
    role: str | None = None
    token: str | None = None
    start: int | None = None
    end: int | None = None
    line: int | None = None
    column: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "code", GPCode(self.code))
        if self.role not in (None, "routing", "sequencing"):
            raise ValueError("diagnostic role must be routing, sequencing or None")
        if type(self.message) is not str or type(self.field_path) is not str:
            raise TypeError("diagnostic message and field_path must be strings")
        if self.token is not None and type(self.token) is not str:
            raise TypeError("diagnostic token must be a string or None")
        positions = (self.start, self.end, self.line, self.column)
        if any(v is not None for v in positions):
            if not all(type(v) is int for v in positions):
                raise ValueError("provide all four integer source coordinates or none")
            if not (0 <= self.start <= self.end and self.line >= 1 and self.column >= 1):
                raise ValueError("invalid source coordinates")

    @classmethod
    def at_source(cls, code, message, *, text, start, end, field_path, role=None):
        """Attach a half-open character span; CRLF is one line break.

        A position on either character of CRLF belongs to the preceding line;
        the following character starts the next line. Tabs occupy one column.
        """
        if type(text) is not str:
            raise TypeError("source text must be a string")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(text):
            raise ValueError("source span is outside text")
        line, column, index = 1, 1, 0
        while index < start:
            ch = text[index]
            if ch == "\r" and index + 1 < len(text) and text[index + 1] == "\n":
                if index + 1 == start:
                    break
                index += 2
                line, column = line + 1, 1
            elif ch in "\r\n":
                index += 1
                line, column = line + 1, 1
            else:
                index += 1
                column += 1
        return cls(code, message, field_path, role, text[start:end], start, end, line, column)

    def to_dict(self):
        result = asdict(self)
        result["code"] = self.code.value
        return result


class GPInputError(InputError):
    def __init__(self, diagnostic: GPDiagnostic):
        self.diagnostic = diagnostic
        self.code = self.reason_code = diagnostic.code.value
        super().__init__(f"{self.code}: {diagnostic.field_path}: {diagnostic.message}")


class GPStateError(StateError):
    def __init__(self, diagnostic: GPDiagnostic):
        self.diagnostic = diagnostic
        self.code = self.reason_code = diagnostic.code.value
        super().__init__(f"{self.code}: {diagnostic.field_path}: {diagnostic.message}")
