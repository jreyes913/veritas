from __future__ import annotations

import re
from dataclasses import dataclass

_STARTERS = re.compile(
    r'^\s*('
    r'This is the program'   r'|'
    r'End of the program'    r'|'
    r'Include the'           r'|'
    r'Define the function'   r'|'
    r'End function'          r'|'
    r'Create '               r'|'
    r'For every iteration'   r'|'
    r'End iteration'         r'|'
    r'If '                   r'|'
    r'Otherwise'             r'|'
    r'End if'                r'|'
    r'Replace '              r'|'
    r'Call '                 r'|'
    r'Load '                 r'|'
    r'Save '
    r')'
)


@dataclass
class Token:
    kind: str
    value: str
    line: int


def strip_comments(src: str) -> str:
    return re.sub(r'/\*.*?\*/', '', src, flags=re.DOTALL)


def logical_lines(src: str) -> list[tuple[int, str]]:
    physical = [(i + 1, ln.strip()) for i, ln in enumerate(src.splitlines()) if ln.strip()]
    logical: list[tuple[int, str]] = []
    current_line = 0
    current: list[str] = []

    for line_no, line in physical:
        if _STARTERS.match(line):
            if current:
                logical.append((current_line, ' '.join(current)))
            current_line = line_no
            current = [line]
        else:
            if not current:
                current_line = line_no
            current.append(line)

    if current:
        logical.append((current_line, ' '.join(current)))

    return logical


def tokenize(src: str) -> list[Token]:
    tokens = [Token(kind='STATEMENT', value=stmt, line=line) for line, stmt in logical_lines(strip_comments(src))]
    tokens.append(Token(kind='EOF', value='', line=(tokens[-1].line if tokens else 1)))
    return tokens


def format_tokens(tokens: list[Token]) -> str:
    return '\n'.join(f"{tok.line:>4}  {tok.kind:<10} {tok.value}" for tok in tokens)
