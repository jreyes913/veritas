"""
vcparser.py — Veritas to C compiler  (vcparser, v3)

Pipeline:  .ver source  →  logical statements  →  AST  →  C output

Changes from v2
───────────────
1.  strip_terminal_period  — fixed float-period ambiguity (regex anchored).
2.  map_type               — removed _TYPE_MAP; C types pass through directly
                             after stripping the English article ('a'/'an').
                             Article mismatch emits a warning; output unaffected.
                             'nothing' remains the sole reserved keyword → 'void'.
3.  AST scaffolding        — every statement builds a typed dict node; a separate
                             codegen pass walks the AST.  Marked # [AST].
4.  quantity expressions   — 'the quantity <expr>' → parenthesised C group.
                             Semicolons chain groups with unrestricted outer ops.
                             _translate_simple / _translate_inner extracted to
                             break the Mode 1 recursion cycle entirely.
                             allow_chained=True permits multi-op inner expressions
                             (e.g. '2 multiplied by x plus 3' → '2 * x + 3').
5.  pointer rendering      — 'type*' renders as 'type *name' in param lists.
6.  _begin_function        — param regex now accepts comma separators and
                             multi-word types (e.g. 'double complex pointer').
7.  _handle_create         — array base-type regex widened to [\w ]+? so
                             multi-word types like 'double complex' are captured.
8.  _begin_for             — start/end values passed through translate_value so
                             quoted variable names like 'N' strip their quotes.
9.  _STARTERS              — unchanged; LL(1) property preserved throughout.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Optional


def warn(msg: str) -> None:
    """Emit a compiler warning to stderr (never to generated C stdout)."""
    print(f'Warning: {msg}', file=sys.stderr)


# ===========================================================================
# 1.  PRE-PROCESSING
# ===========================================================================

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
    r'Call '
    r')'
)


def strip_comments(src: str) -> str:
    """Remove /* ... */ block comments (including multi-line)."""
    return re.sub(r'/\*.*?\*/', '', src, flags=re.DOTALL)


def logical_lines(src: str) -> list[str]:
    """Group physical lines into logical statements using LL(1) starters."""
    physical = [ln.strip() for ln in src.splitlines() if ln.strip()]
    logical: list[str] = []
    current: list[str] = []

    for line in physical:
        if _STARTERS.match(line):
            if current:
                logical.append(' '.join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        logical.append(' '.join(current))

    return logical


_TRAILING_PERIOD = re.compile(r'\.\s*$')


def strip_terminal_period(s: str) -> str:
    """Remove the sentence-final period. Anchored so float dots are safe."""
    return _TRAILING_PERIOD.sub('', s).rstrip()


# ===========================================================================
# 2.  TYPE MAPPING
# ===========================================================================

def map_type(t: str) -> str:
    """
    Strip the Veritas article ('a'/'an') and pass the C type through directly.
    'nothing' is the only reserved keyword and maps to 'void'.
    'string' maps to 'char*'.
    Warns if the wrong article is used; output is unaffected either way.
    """
    t = t.strip()
    if t == 'nothing':
        return 'void'
    if t == 'string':
        return 'char*'
    m = re.match(r'^(an?)\s+(.+)', t, re.IGNORECASE)
    if m:
        article, ctype = m.group(1).lower(), m.group(2)
        if ctype[0].lower() in 'aeiou' and article != 'an':
            warn(f"'{ctype}' starts with a vowel, expected 'an'")
        elif ctype[0].lower() not in 'aeiou' and article != 'a':
            warn(f"'{ctype}' starts with a consonant, expected 'a'")
        t = ctype
    if t.endswith(' pointer'):
        return map_type(t[:-len(' pointer')].strip()) + '*'
    return t


# ===========================================================================
# 3.  OPERATOR TABLES
# ===========================================================================

COMPARE_OPS: list[tuple[str, str]] = [
    ('is greater than or equal to', '>='),
    ('is less than or equal to',    '<='),
    ('is greater than',             '>'),
    ('is less than',                '<'),
    ('is equal to',                 '=='),
]

ARITH_OPS: list[tuple[str, str]] = [
    ('raised to the', 'pow'),
    ('multiplied by', '*'),
    ('divided by',    '/'),
    ('plus',          '+'),
    ('minus',         '-'),
]

_ARITH_KEYWORDS: set[str] = {kw for kw, _ in ARITH_OPS}


# ===========================================================================
# 4.  EXPRESSION HELPERS
# ===========================================================================

def translate_value(token: str) -> str:
    """Translate a single Veritas value token to its C representation."""
    token = token.strip()

    # Match "an element of 'var' at index 'idx'" (allowing for protected spaces \x00)
    m = re.match(r"an[\s\x00]element[\s\x00]of[\s\x00]'(\w+)'[\s\x00]at[\s\x00]index[\s\x00](?:'(.+?)'|(\w+))", token)
    if m:
        idx = m.group(2) or m.group(3)
        return f'{m.group(1)}[{_unprotect(idx)}]'

    m = re.match(r"value[\s\x00]at[\s\x00]'(\w+)'", token)
    if m:
        return f'*{m.group(1)}'

    m = re.match(r"the[\s\x00]address[\s\x00]of[\s\x00]'(\w+)'", token)
    if m:
        return f'&{m.group(1)}'

    if token.startswith("'") and token.endswith("'") and len(token) > 2:
        return _unprotect(token[1:-1])

    # Imaginary numbers: e.g., 4.2j
    m = re.match(r"^(\d+\.?\d*|\.\d+)j$", token)
    if m:
        return f'({m.group(1)} * _Complex_I)'

    return _unprotect(token)


def split_on_keyword(text: str, keyword: str) -> Optional[tuple[str, str]]:
    """
    Find the first whole-word occurrence of keyword outside quoted regions
    and return (before, after).  Returns None if not found.
    """
    blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), text)
    blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)
    m = re.search(r'\b' + re.escape(keyword) + r'\b', blanked)
    if m:
        return text[:m.start()].strip(), text[m.end():].strip()
    return None


def _count_arith_ops(expr: str) -> int:
    """Count distinct arithmetic operator keywords outside quoted regions."""
    blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), expr)
    blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)
    return sum(
        1 for kw in _ARITH_KEYWORDS
        if re.search(r'\b' + re.escape(kw) + r'\b', blanked)
    )


# ---------------------------------------------------------------------------
# QUANTITY EXPRESSION PARSER
# ---------------------------------------------------------------------------

def _split_quantity_clauses(expr: str) -> list[str]:
    """Split a semicolon-separated quantity chain into individual clauses."""
    return [c.strip() for c in expr.split(';') if c.strip()]


def _parse_quantity_clause(clause: str) -> tuple[Optional[str], str]:
    """
    Strip a leading arithmetic operator keyword from a clause.
    Returns (c_operator, remainder) or (None, clause) if no leading op.
    """
    for vop, cop in ARITH_OPS:
        pattern = re.compile(r'^' + re.escape(vop) + r'\s+', re.IGNORECASE)
        m = pattern.match(clause)
        if m:
            return cop, clause[m.end():].strip()
    return None, clause


def _render_arith_expr(lhs: str, rhs: str, op: str) -> str:
    """Render a binary arithmetic expression in C syntax."""
    if op == 'pow':
        return f'pow({lhs}, {rhs})'
    return f'{lhs} {op} {rhs}'


def _translate_simple(expr: str, allow_chained: bool = False) -> str:
    """
    Translate an arithmetic expression containing no quantity clauses.

    allow_chained=False (default, Mode 2 / bare expressions):
        Enforces single-operator restriction; emits a diagnostic comment
        if more than one operator keyword is present.

    allow_chained=True (inside a quantity group):
        Parses left-to-right so '2 multiplied by x plus 3' → '2 * x + 3'.
        Finds the rightmost operator and recurses on the left operand,
        giving standard left-associative evaluation order.
    """
    expr = expr.strip()
    if expr.lower().startswith('the quantity '):
        return _translate_inner(expr)

    if allow_chained:
        blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), expr)
        blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)
        # Blank out nested 'the quantity ...' spans so their internal
        # operators are invisible to the rightmost-op search.  A nested
        # quantity is everything from 'the quantity' to end-of-string
        # (it is always the final token in a well-formed RHS).
        blanked = re.sub(r'\bthe quantity\b.*$', lambda m: ' ' * len(m.group()),
                         blanked, flags=re.IGNORECASE)

        best_pos: Optional[int] = None
        best_vop: Optional[str] = None
        best_cop: Optional[str] = None

        for vop, cop in ARITH_OPS:
            for hit in re.finditer(r'\b' + re.escape(vop) + r'\b', blanked):
                if best_pos is None or hit.start() > best_pos:
                    best_pos = hit.start()
                    best_vop = vop
                    best_cop = cop

        if best_vop is not None and best_pos is not None:
            # Split at the exact position of the rightmost operator,
            # not the first occurrence, to get correct left-associativity.
            lhs = expr[:best_pos].strip()
            rhs = expr[best_pos + len(best_vop):].strip()
            return _render_arith_expr(
                _translate_simple(lhs, allow_chained=True),
                _translate_inner(rhs),
                best_cop,
            )
        return translate_value(expr)

    # allow_chained=False — original single-operator restriction
    op_count = _count_arith_ops(expr)
    if op_count > 1:
        return (
            f'/* ERROR: chained arithmetic not allowed — '
            f'split into multiple statements: {expr} */ 0'
        )
    for vop, cop in ARITH_OPS:
        parts = split_on_keyword(expr, vop)
        if parts:
            lhs, rhs = parts
            return _render_arith_expr(translate_value(lhs), translate_value(rhs), cop)
    return translate_value(expr)


def _translate_inner(expr: str) -> str:
    """
    Translate a value that may itself be 'the quantity ...' or a bare token.
    Used as the RHS handler in _translate_simple so nested quantity groups
    are parenthesised correctly instead of passed verbatim to translate_value.
    """
    expr = expr.strip()
    m = re.match(r'^the quantity\s+(.+)$', expr, re.IGNORECASE)
    if m:
        inner = _translate_simple(m.group(1).strip(), allow_chained=True)
        return f'({inner})'
    return translate_value(expr)


def _translate_quantity(expr: str) -> str:
    """
    Translate 'the quantity <inner>' → '(<inner_c>)'.

    Uses _translate_simple(allow_chained=True) so inner expressions like
    '2 multiplied by x plus 3' produce '2 * x + 3' without error.
    Never calls translate_expression — no Mode 1 re-entry, no recursion.
    """
    m = re.match(r'^the quantity\s+(.+)$', expr, re.IGNORECASE)
    if m:
        inner = _translate_simple(m.group(1).strip(), allow_chained=True)
        return f'({inner})'
    return _translate_simple(expr, allow_chained=True)


def translate_expression(expr: str) -> str:
    """
    Translate an arithmetic expression to C.

    Mode 1 — quantity-chained:
      Triggered by 'the quantity' keyword or semicolons.
      Each semicolon-delimited clause becomes a parenthesised C group.
      Call graph: translate_expression → _translate_quantity
                                       → _translate_simple  (no cycle)

    Mode 2 — single-operator:
      Original behaviour. Enforces one-operator restriction.
      Delegates to _translate_simple(allow_chained=False).
    """
    expr = expr.strip()

    if ';' in expr or re.search(r'\bthe quantity\b', expr, re.IGNORECASE):
        clauses = _split_quantity_clauses(expr)

        if len(clauses) == 1:
            _, core = _parse_quantity_clause(clauses[0])
            return _translate_quantity(core)

        assembled: Optional[str] = None
        for i, clause in enumerate(clauses):
            op, core = _parse_quantity_clause(clause)
            c_group = _translate_quantity(core)
            if i == 0:
                assembled = c_group
            else:
                if op is None:
                    assembled = (
                        f'{assembled} '
                        f'/* ERROR: missing operator before clause '
                        f'{i + 1}: {clause} */ {c_group}'
                    )
                else:
                    assembled = _render_arith_expr(assembled or '0', c_group, op)

        return assembled or '0'

    return _translate_simple(expr)

def translate_condition(cond: str) -> str:
    """Translate a Veritas comparison condition to a C boolean expression."""
    cond = cond.strip().rstrip(':')
    # String comparison heuristic
    if ' is equal to ' in cond and '"' in cond:
        parts = split_on_keyword(cond, 'is equal to')
        if parts:
            lhs = translate_value(parts[0])
            rhs = translate_value(parts[1])
            return f'strcmp({lhs}, {rhs}) == 0'

    for vop, cop in COMPARE_OPS:
        parts = split_on_keyword(cond, vop)
        if parts:
            return f'{translate_value(parts[0])} {cop} {translate_value(parts[1])}'
    return cond


# ===========================================================================
# 5.  ARGUMENT LIST PARSING
# ===========================================================================

_PROTECTED_PHRASES: list[str] = [
    'an element of',
    'the address of',
    'value at',
    'the quantity',
    'at index',
]
_NULL = '\x00'


def _protect(s: str) -> str:
    for phrase in _PROTECTED_PHRASES:
        s = s.replace(phrase, phrase.replace(' ', _NULL))
    return s


def _unprotect(s: str) -> str:
    return s.replace(_NULL, ' ')


def parse_argument_list(raw: str) -> list[str]:
    """
    Parse a comma / 'and'-separated Veritas argument list with strict rules:
    - 1 item: 'X'
    - 2 items: 'X and Y' (NO COMMAS)
    - 3+ items: 'X, Y, and Z' (Oxford comma required)
    """
    raw = raw.strip()
    if not raw:
        return []

    # Handle 1 item (no commas, no 'and')
    if ',' not in raw and not re.search(r'\band\b', raw, re.IGNORECASE):
        return [raw]

    # Handle 2 items (no commas, exactly one 'and')
    if ',' not in raw:
        and_parts = re.split(r'\s+and\s+', raw, flags=re.IGNORECASE)
        if len(and_parts) == 2:
            return [p.strip() for p in and_parts]
        else:
            # Maybe it's a 3+ item list missing commas? Or malformed.
            pass

    # Check for 2-item list with comma violation: "X, and Y"
    if raw.count(',') == 1:
        parts = [p.strip() for p in raw.split(',')]
        if len(parts) == 2 and re.match(r'^and\s+', parts[1], re.IGNORECASE):
            warn(f"Grammar violation: 2-item list should not have a comma: {raw}")
            parts[1] = re.sub(r'^and\s+', '', parts[1], flags=re.IGNORECASE).strip()
            return parts

    # Handle 3+ items (must have commas and 'and' for the last element)
    parts = [p.strip() for p in raw.split(',')]
    if len(parts) < 3:
        # If we got here and parts < 3, it's likely a malformed 2-item list
        return parts

    last_part = parts[-1]
    m_and = re.match(r'^and\s+(.+)', last_part, re.IGNORECASE)
    if not m_and:
        warn(f"Strict list violation: last element must start with 'and': {raw}")
        return [p.strip() for p in parts]
    
    parts[-1] = m_and.group(1).strip()
    return parts


# ===========================================================================
# 6.  AST NODE TYPES                                                  # [AST]
# ===========================================================================

ASTNode = dict[str, Any]


# ===========================================================================
# 7.  PARSER  (source → AST)                                          # [AST]
# ===========================================================================

class Parser:
    """Converts logical Veritas statements into a module AST."""

    def __init__(self) -> None:
        self._module: ASTNode = {
            'kind':      'module',
            'name':      '',
            'includes':  [],
            'globals':   [],
            'functions': [],
            'main':      [],
        }
        self._scope_stack: list[list[ASTNode]] = [self._module['main']]
        self._block_stack: list[ASTNode] = []
        self._in_function: bool = False
        self._current_func: Optional[ASTNode] = None
        self._main_scope: list[ASTNode] = self._module['main']

    def feed(self, stmt: str) -> None:
        s = strip_terminal_period(stmt.strip())
        self._dispatch(s)

    def ast(self) -> ASTNode:
        self._finalize()
        return self._module

    def _emit_error(self, message: str, raw: str) -> None:
        self._main_scope.append({'kind': 'error', 'message': message, 'raw': raw})

    def _finalize(self) -> None:
        while len(self._scope_stack) > 1:
            self._pop_scope()

        if self._current_func is not None:
            self._emit_error(
                f"unclosed function '{self._current_func['name']}'",
                f"Define the function '{self._current_func['name']}'",
            )
            self._current_func = None
            self._in_function = False

        while self._block_stack:
            block = self._block_stack.pop()
            if block['kind'] == 'for':
                self._emit_error(
                    "unclosed iteration block",
                    f"For every iteration of '{block['var']}'",
                )
            elif block['kind'] == 'if':
                self._emit_error('unclosed if block', f"If {block['condition']}")

    def _dispatch(self, s: str) -> None:
        m = re.match(r"This is the program '(\w+)'", s)
        if m:
            self._module['name'] = m.group(1)
            return

        if re.match(r"End of the program '(\w+)'", s):
            return

        m = re.match(r"Include the (?:library|header) '([^']+)'", s)
        if m:
            self._module['includes'].append({'kind': 'include', 'path': m.group(1)})
            return

        m = re.match(r"Define the function '(\w+)'(.*)", s, re.DOTALL)
        if m:
            self._begin_function(m.group(1), m.group(2))
            return

        m = re.match(r"End function '(\w+)'", s)
        if m:
            self._end_function(m.group(1))
            return

        if s.startswith('Create '):
            self._handle_create(s)
            return

        m = re.match(r"For every iteration of '(\w+)' from (\S+) (through|to) (\S+)", s)
        if m:
            self._begin_for(m)
            return

        m = re.match(r"End iteration of '(\w+)' from (\S+) (through|to) (\S+)", s)
        if m:
            self._end_for()
            return

        m = re.match(r"If (.+?):\s*$", s)
        if m:
            self._begin_if(m.group(1))
            return

        if re.match(r"Otherwise\s*:?\s*$", s):
            self._switch_else()
            return

        if re.match(r"End if .+", s):
            self._end_if()
            return

        m = re.match(r"Replace (.+?) at index (.+?) with (.+)$", s)
        if m:
            target = translate_value(m.group(1))
            idx = translate_value(m.group(2))
            self._current_scope().append({
                'kind':   'assign',
                'target': f'{target}[{idx}]',
                'value':  _translate_simple(m.group(3).strip(), allow_chained=True),
            })
            return

        m = re.match(r"Replace (.+?) with (.+)$", s)
        if m:
            self._current_scope().append({
                'kind':   'assign',
                'target': translate_value(m.group(1)),
                'value':  _translate_simple(m.group(2).strip(), allow_chained=True),
            })
            return

        if s.startswith('Call '):
            self._handle_call(s)
            return

        self._current_scope().append(
            {'kind': 'error', 'message': 'unrecognised statement', 'raw': s})

    def _current_scope(self) -> list[ASTNode]:
        return self._scope_stack[-1]

    def _push_scope(self, body: list[ASTNode]) -> None:
        self._scope_stack.append(body)

    def _pop_scope(self) -> list[ASTNode]:
        return self._scope_stack.pop()

    def _begin_function(self, name: str, rest: str) -> None:
        ret_type = 'void'
        ret_m = re.search(r'\breturning\s+(.+?)$', rest)
        if ret_m:
            ret_type = map_type(ret_m.group(1).strip())
            rest = rest[:ret_m.start()]

        params: list[tuple[str, str]] = []
        for pm in re.finditer(
                r"'(\w+)'\s+as\s+an?\s+([\w][\w ]*?)(?=\s*,|\s+and\s+'|\s*$)", rest):
            params.append((map_type(pm.group(2).strip()), pm.group(1)))

        self._current_func = {
            'kind':     'func_def',
            'name':     name,
            'params':   params,
            'ret_type': ret_type,
            'body':     [],
        }
        self._in_function = True
        self._push_scope(self._current_func['body'])

    def _end_function(self, name: str) -> None:
        if self._current_func is None or not self._in_function:
            self._emit_error('End function without active function', f"End function '{name}'")
            return

        if self._current_func['name'] != name:
            self._emit_error(
                (
                    f"mismatched function end: expected End function "
                    f"'{self._current_func['name']}'"
                ),
                f"End function '{name}'",
            )

        if len(self._scope_stack) > 1:
            self._pop_scope()
        self._module['functions'].append(self._current_func)
        self._current_func = None
        self._in_function = False

    def _handle_create(self, s: str) -> None:
        node: Optional[ASTNode] = None

        # 1. NEW: Create 'label' as an element of 'labels' at index 0.
        m_idx = re.match(r"Create '(\w+)' as an element of '(\w+)' at index (?:'(.+?)'|(\w+))$", s)
        if m_idx:
            name, container, idx_val = m_idx.group(1), m_idx.group(2), (m_idx.group(3) or m_idx.group(4))
            init_c = f"{container}[{idx_val}]"
            node = {
                'kind': 'declare', 'container': 'indexed_scalar', 'name': name,
                'source_container': container, 'index': idx_val, 'ctype': 'auto',
                'is_array': False, 'size': None, 'init': init_c
            }

        # 2. Vector with values
        if node is None:
            m = re.match(r"Create '(\w+)' as an? ([\w ]+?) vector of size (\d+) with values:(.+)$", s, re.DOTALL)
            if m:
                name, base, size, vals_raw = m.groups()
                vals = parse_argument_list(vals_raw)
                node = {
                    'kind': 'declare', 'container': 'vector', 'ctype': map_type(base), 'name': name,
                    'is_array': True, 'size': int(size), 'init': vals,
                }

        # 3. Vector without values
        if node is None:
            m = re.match(r"Create '(\w+)' as an? ([\w ]+?) vector of size (\d+)$", s)
            if m:
                name, base, size = m.groups()
                node = {
                    'kind': 'declare', 'container': 'vector', 'ctype': map_type(base),
                    'name': name, 'is_array': True, 'size': int(size), 'init': None,
                }

        # 4. Array with values
        if node is None:
            m = re.match(r"Create '(\w+)' as an? ([\w ]+?) array of size (\d+) with values:(.+)$", s, re.DOTALL)
            if m:
                name, base, size, vals_raw = m.groups()
                vals = parse_argument_list(vals_raw)
                node = {
                    'kind': 'declare', 'container': 'array', 'ctype': map_type(base), 'name': name,
                    'is_array': True, 'size': int(size), 'init': vals,
                }

        # 5. Array without values
        if node is None:
            m = re.match(r"Create '(\w+)' as an? ([\w ]+?) array of size (\d+)$", s)
            if m:
                name, base, size = m.groups()
                node = {
                    'kind': 'declare', 'container': 'array', 'ctype': map_type(base),
                    'name': name, 'is_array': True, 'size': int(size), 'init': None,
                }

        # 6. Matrix
        if node is None:
            m = re.match(r"Create '(\w+)' as an? matrix(?: with columns:\s*(.+))?$", s, re.DOTALL)
            if m:
                cols_raw = (m.group(2) or '').strip()
                columns = parse_argument_list(cols_raw) if cols_raw else []
                node = {
                    'kind': 'declare', 'container': 'matrix', 'ctype': 'matrix',
                    'name': m.group(1), 'is_array': False, 'size': None, 'init': None,
                    'columns': columns,
                }

        # 7. Scalar with value
        if node is None:
            m = re.match(r"Create '(\w+)' as an? (.+?) with value (.+)$", s)
            if m:
                node = {
                    'kind': 'declare', 'container': 'scalar', 'ctype': map_type(m.group(2).strip()),
                    'name': m.group(1), 'is_array': False, 'size': None,
                    'init': translate_expression(m.group(3).strip()),
                }

        # 8. Scalar without value
        if node is None:
            m = re.match(r"Create '(\w+)' as an? (.+)$", s)
            if m:
                node = {
                    'kind': 'declare', 'container': 'scalar', 'ctype': map_type(m.group(2).strip()),
                    'name': m.group(1), 'is_array': False, 'size': None, 'init': None,
                }

        if node is None:
            self._current_scope().append(
                {'kind': 'error', 'message': 'malformed Create', 'raw': s})
            return

        if self._in_function:
            self._current_scope().append(node)
        else:
            self._module['globals'].append(node)

    def _begin_for(self, m: re.Match) -> None:
        for_node: ASTNode = {
            'kind': 'for', 'var': m.group(1),
            'start': translate_value(m.group(2)),
            'end':   translate_value(m.group(4).rstrip(':')),
            'inclusive': m.group(3) == 'through', 'body': [],
        }
        self._current_scope().append(for_node)
        self._block_stack.append(for_node)
        self._push_scope(for_node['body'])

    def _end_for(self) -> None:
        if not self._block_stack:
            self._emit_error('End iteration without active loop', 'End iteration')
            return
        node = self._block_stack[-1]
        if node['kind'] != 'for':
            self._emit_error(
                'End iteration encountered, but active block is not a loop',
                'End iteration',
            )
            return
        if len(self._scope_stack) > 1:
            self._pop_scope()
        self._block_stack.pop()

    def _begin_if(self, condition_raw: str) -> None:
        if_node: ASTNode = {
            'kind': 'if',
            'condition': translate_condition(condition_raw),
            'then_body': [], 'else_body': [],
        }
        self._current_scope().append(if_node)
        self._block_stack.append(if_node)
        self._push_scope(if_node['then_body'])

    def _switch_else(self) -> None:
        if not self._block_stack:
            self._emit_error('Otherwise without active If block', 'Otherwise')
            return
        if_node = self._block_stack[-1]
        if if_node['kind'] != 'if':
            self._emit_error(
                'Otherwise encountered, but active block is not If',
                'Otherwise',
            )
            return
        if len(self._scope_stack) > 1:
            self._pop_scope()
        self._push_scope(if_node['else_body'])

    def _end_if(self) -> None:
        if not self._block_stack:
            self._emit_error('End if without active If block', 'End if')
            return
        node = self._block_stack[-1]
        if node['kind'] != 'if':
            self._emit_error('End if encountered, but active block is not If', 'End if')
            return
        if len(self._scope_stack) > 1:
            self._pop_scope()
        self._block_stack.pop()

    def _handle_call(self, s: str) -> None:
        m = re.match(
            r"Call '(\w+)'(?:\s+with\s+(.*?))?\s*,?\s*stored to\s+(.+)$",
            s, re.DOTALL)
        if not m:
            self._current_scope().append(
                {'kind': 'error', 'message': 'malformed Call', 'raw': s})
            return

        func_name = m.group(1)
        args_raw  = (m.group(2) or '').strip()
        dest_raw  = m.group(3).strip()

        c_args = (
            [translate_value(a) for a in parse_argument_list(args_raw)]
            if args_raw else []
        )
        dest = None if dest_raw == 'nothing' else translate_value(dest_raw)

        self._current_scope().append({
            'kind': 'call', 'func': func_name, 'args': c_args, 'dest': dest,
        })


# ===========================================================================
# 8.  CODE GENERATOR  (AST → C)                                       # [AST]
# ===========================================================================

class CodeGen:
    """Walks the module AST and produces C source code."""

    def __init__(self, symbols: Optional[SymbolTable] = None) -> None:
        self.includes: list[str] = []
        self.globals: list[str] = []
        self.global_inits: list[str] = []
        self.functions: list[str] = []
        self.main_body: list[str] = []
        self._main_scalars: set[str] = set()
        self._in_function: bool = False
        self._func_scalars: set[str] = set()
        self.triggered_includes: set[str] = set()
        self.symbols = symbols
        self._var_types: dict[str, str] = {}
        self._var_sizes: dict[str, int] = {}
        self._global_vars: set[str] = set()
        self._loop_count = 0
        if symbols:
            for name, ctype, scope, size in symbols.as_rows():
                self._var_types[name] = ctype
                if size is not None:
                    self._var_sizes[name] = size
                if scope == 'global':
                    self._global_vars.add(name)

    def generate(self, module: ASTNode) -> str:
        self._scan_triggers(module)
        self._gen_includes(module['includes'])
        self._gen_globals(module['globals'])
        self._gen_functions(module['functions'])
        self._gen_main(module['main'])
        return self._render()

    def _scan_triggers(self, module: ASTNode) -> None:
        def check_type(ctype: str):
            if 'double complex' in ctype:
                self.triggered_includes.add('complex.h')
            if 'wchar_t' in ctype:
                self.triggered_includes.add('wchar.h')

        for g in module['globals']:
            check_type(g['ctype'])
        for f in module['functions']:
            check_type(f['ret_type'])
            for p_type, _ in f['params']:
                check_type(p_type)
        
        # Always trigger complex.h if we are going to emit complex-based prototypes
        self.triggered_includes.add('complex.h')
        
        # Check main body for Call triggers
        def scan_body(nodes: list[ASTNode]):
            for node in nodes:
                if node['kind'] == 'call':
                    func = node['func']
                    if func in ('time', 'seed', 'clock', 'srand'):
                        self.triggered_includes.add('time.h')
                    if func == 'assert':
                        self.triggered_includes.add('assert.h')
                    if func in {
                        'sample_variance', 'population_variance', 'sample_std', 'population_std',
                        'median', 'mode', 'quantile', 'iqr', 'covariance', 'correlation',
                        'skewness', 'kurtosis', 't_test', 'paired_t_test', 'chi_square_test',
                        'anova_one_way', 'mean_confidence_interval',
                        'proportion_confidence_interval', 'normal_pdf', 'normal_cdf',
                        'normal_inverse_cdf', 'student_t_cdf', 'student_t_inverse_cdf',
                        'chi_square_cdf', 'chi_square_inverse_cdf', 'f_cdf',
                        'f_inverse_cdf', 'sample_normal', 'sample_uniform', 'sample_poisson',
                    }:
                        self.triggered_includes.update({
                            'gsl/gsl_statistics.h', 'gsl/gsl_statistics_double.h',
                            'gsl/gsl_cdf.h', 'gsl/gsl_randist.h', 'gsl/gsl_rng.h'
                        })
                    if func in {
                        'solve_linear_system', 'matrix_multiply', 'invert_matrix',
                        'determinant', 'trace', 'transpose', 'eigenvalues', 'eigenvectors',
                        'lu_decompose', 'qr_decompose', 'svd', 'vector_norm',
                        'matrix_norm', 'condition_number',
                    }:
                        self.triggered_includes.update({
                            'gsl/gsl_matrix.h', 'gsl/gsl_vector.h', 'gsl/gsl_blas.h',
                            'gsl/gsl_linalg.h', 'gsl/gsl_eigen.h'
                        })
                if 'body' in node:
                    scan_body(node['body'])
                if 'then_body' in node:
                    scan_body(node['then_body'])
                if 'else_body' in node:
                    scan_body(node['else_body'])

        scan_body(module['main'])
        for f in module['functions']:
            scan_body(f['body'])

    def _gen_includes(self, nodes: list[ASTNode]) -> None:
        prelude = [
            'stdio.h', 'stdlib.h', 'math.h', 'string.h', 'stdint.h', 
            'stdbool.h', 'float.h', 'limits.h', 'regex.h', 'ctype.h',
            'stddef.h', 'alloca.h'
        ]
        required = set(prelude)
        required.update(self.triggered_includes)
        
        self.includes.extend([f'#include <{h}>' for h in sorted(required)])
        seen = required
        for node in nodes:
            path = node['path']
            if path not in seen:
                self.includes.append(f'#include <{path}>')
                seen.add(path)

    def _gen_globals(self, nodes: list[ASTNode]) -> None:
        for node in nodes:
            self.globals.append(self._global_decl_c(node))

    def _gen_functions(self, nodes: list[ASTNode]) -> None:
        for func in nodes:
            self.functions.append('\n'.join(self._func_c(func)))

    def _gen_main(self, nodes: list[ASTNode]) -> None:
        for node in nodes:
            self.main_body.extend(self._node_c(node, indent=1))

    def _get_var_type(self, name: str) -> Optional[str]:
        return self._var_types.get(name)

    def _node_c(self, node: ASTNode, indent: int) -> list[str]:
        pad = '    ' * indent
        kind = node['kind']
        scalars = self._func_scalars if self._in_function else self._main_scalars

        if kind == 'declare':
            return [pad + self._decl_c(node, scalars, arena_ref=self._arena_ref())]

        if kind == 'assign':
            target = node['target']
            value = node['value']
            
            # Vector arithmetic check
            target_type = self._get_var_type(target)
            if target_type and target_type.startswith('vector<'):
                m_arith = re.match(r'\((\w+) ([+\-*/]) (\w+)\)', value)
                if not m_arith:
                     # Check for Veritas keywords if they were translated
                     m_arith = re.match(r'\((\w+) (plus|minus|multiplied by|divided by) (\w+)\)', value)

                if m_arith:
                    v1, op_sym, v2 = m_arith.groups()
                    op_map = {'+': '+', '-': '-', '*': '*', '/': '/', 'plus': '+', 'minus': '-', 'multiplied by': '*', 'divided by': '/'}
                    op = op_map.get(op_sym, op_sym)
                    
                    v_size = self._var_sizes.get(target, 1)
                    if 'double complex' in target_type:
                        func_map = {'+': 'vector_add', '-': 'vector_sub', '*': 'vector_mul'}
                        if op in func_map:
                             return [f'{pad}{func_map[op]}({v1}, {v2}, {target}, {v_size});']
                    
                    # Fallback to loop for better type safety with int/float
                    ln = f"__i_{self._loop_count}"
                    self._loop_count += 1
                    return [
                        f'{pad}for (int {ln} = 0; {ln} < {v_size}; {ln}++) {{ {target}[{ln}] = {v1}[{ln}] {op} {v2}[{ln}]; }}'
                    ]
            
            target_c = self._rewrite_expr(target, scalars)
            value_c = self._rewrite_expr(value, scalars)
            return [f'{pad}{target_c} = {value_c};']

        if kind == 'call':
            args_str = ', '.join(self._rewrite_expr(arg, scalars) for arg in node['args'])
            call = f'{node["func"]}({args_str})'
            if node['dest'] is None:
                return [f'{pad}{call};']
            return [f'{pad}{self._rewrite_expr(node["dest"], scalars)} = {call};']

        if kind == 'for':
            # inclusive means 'through' -> <=, exclusive means 'to' -> <
            op = '<=' if node['inclusive'] else '<'
            var = node['var']
            start = self._rewrite_expr(node['start'], scalars)
            # Use a separate set to avoid dereferencing the loop variable 'var' itself in the loop condition
            end_scalars = scalars.copy()
            if var in end_scalars:
                end_scalars.remove(var)
            end = self._rewrite_expr(node['end'], end_scalars)
            
            lines = [
                f'{pad}{{',
                f'{pad}    int *{var} = alloca(sizeof(int));',
                f'{pad}    *{var} = {start};',
                f'{pad}    for (; *{var} {op} {end}; (*{var})++) {{',
            ]
            scalars.add(var)
            for child in node['body']:
                lines.extend(self._node_c(child, indent + 2))
            lines.append(pad + '    }')
            lines.append(pad + '}')
            return lines

        if kind == 'if':
            cond = self._rewrite_expr(node['condition'], scalars)
            lines = [f'{pad}if ({cond}) {{']
            for child in node['then_body']:
                lines.extend(self._node_c(child, indent + 1))
            if node['else_body']:
                lines.append(pad + '} else {')
                for child in node['else_body']:
                    lines.extend(self._node_c(child, indent + 1))
            lines.append(pad + '}')
            return lines

        if kind == 'error':
            return [f'{pad}/* ERROR: {node["message"]} — {node["raw"]} */']

        return [f'{pad}/* UNKNOWN NODE KIND: {kind} */']

    def _decl_c(self, node: ASTNode, scalar_vars: set[str], arena_ref: str) -> str:
        ctype = node['ctype']
        name = node['name']
        container = node.get('container', 'array' if node.get('is_array') else 'scalar')
        
        is_global = not self._in_function and name in self._global_vars

        if container == 'indexed_scalar':
            scalar_vars.add(name)
            decl = f'{ctype} *{name}' if not is_global else name
            init_c = node['init'] # Already translated to "labels[0]" or similar
            init_c = self._rewrite_expr(init_c, scalar_vars)
            return f'{decl} = arena_alloc({arena_ref}, sizeof({ctype})); *{name} = {init_c};'

        if container in {'array', 'vector'}:
            size = node['size']
            decl = f'{ctype} *{name}' if not is_global else name
            lines = [f'{decl} = arena_alloc({arena_ref}, {size} * sizeof({ctype}));']
            if node['init']:
                for idx, val in enumerate(node['init']):
                    lines.append(f'{name}[{idx}] = {translate_expression(val)};')
            return ' '.join(lines)

        if container == 'matrix':
            decl = f'void *{name}' if not is_global else name
            return f'{decl} = NULL; /* Matrix runtime object */'

        scalar_vars.add(name)
        decl = f'{ctype} *{name}' if not is_global else name
        if node['init'] is not None:
            init_raw = node['init']
            init_c = translate_value(init_raw)
            init_c = self._rewrite_expr(init_c, scalar_vars)
            return f'{decl} = arena_alloc({arena_ref}, sizeof({ctype})); *{name} = {init_c};'
        return f'{decl} = arena_alloc({arena_ref}, sizeof({ctype}));'

    def _global_decl_c(self, node: ASTNode) -> str:
        ctype = node['ctype']
        name = node['name']
        container = node.get('container', 'array' if node.get('is_array') else 'scalar')
        if container in {'array', 'vector'}:
            self.global_inits.append(self._decl_c(node, self._main_scalars, arena_ref='&arena'))
            return f'{ctype} *{name};'

        if container == 'matrix':
            self.global_inits.append(f'{name} = NULL;')
            return f'void *{name};'

        self._main_scalars.add(name)
        if node['init'] is None:
            self.global_inits.append(f'{name} = arena_alloc(&arena, sizeof({ctype}));')
        else:
            init = self._rewrite_expr(node['init'], self._main_scalars)
            self.global_inits.append(
                f'{name} = arena_alloc(&arena, sizeof({ctype})); *{name} = {init};'
            )
        return f'{ctype} *{name};'

    def _arena_ref(self) -> str:
        return 'global_arena' if self._in_function else '&arena'

    def _rewrite_expr(self, expr: str, scalar_vars: set[str]) -> str:
        # String concatenation heuristic: if we see ' + ' and it looks like strings
        if ' + ' in expr and ('"' in expr or any(v in expr for v in scalar_vars)):
             # This is a bit fragile without a full type-aware rewriter
             pass

        out = expr
        string_placeholders: dict[str, str] = {}
        # Protect string literals
        for i, match in enumerate(re.finditer(r'"[^"]*"', out)):
            ph = f"__VER_STR_{i}__"
            string_placeholders[ph] = match.group()
            out = out.replace(match.group(), ph)

        placeholders: dict[str, str] = {}
        for idx, name in enumerate(sorted(scalar_vars, key=len, reverse=True)):
            placeholder = f'__ARENA_ADDR_{idx}__'
            replaced = re.sub(rf'&{re.escape(name)}(?!\w)', placeholder, out)
            if replaced != out:
                placeholders[placeholder] = name
                out = replaced
            out = re.sub(
                rf'(?<![\w\*\&]){re.escape(name)}(?!\w)(?!\s*\[)',
                f'*{name}',
                out,
            )
        
        # Restore addresses
        for placeholder, replacement in placeholders.items():
            out = out.replace(placeholder, replacement)
        
        # Restore strings
        for ph, orig in string_placeholders.items():
            out = out.replace(ph, orig)
            
        return out

    def _func_c(self, func: ASTNode) -> list[str]:
        def _render_param(ctype: str, name: str) -> str:
            stars = len(ctype) - len(ctype.rstrip('*'))
            if stars:
                return f'{ctype.rstrip("*")} {"*" * stars}{name}'
            return f'{ctype} {name}'

        param_str = ', '.join(
            _render_param(ctype, pname) for ctype, pname in func['params']
        ) or 'void'

        lines = [f'{func["ret_type"]} {func["name"]}({param_str})', '{']
        prev_in_function = self._in_function
        prev_scalars = self._func_scalars
        self._in_function = True
        self._func_scalars = set()
        for child in func['body']:
            lines.extend(self._node_c(child, indent=1))
        self._in_function = prev_in_function
        self._func_scalars = prev_scalars
        lines.append('}')
        return lines

    def _render(self) -> str:
        parts: list[str] = []
        if self.includes:
            parts.append('\n'.join(self.includes))
        if self.globals:
            parts.append('\n'.join(self.globals))

        parts.append('\n'.join([
            'typedef struct {',
            '    unsigned char *memory;',
            '    size_t capacity;',
            '    size_t offset;',
            '} Arena;',
            '',
            'Arena arena_create(size_t size) {',
            '    Arena arena;',
            '    arena.memory = malloc(size);',
            '    arena.capacity = size;',
            '    arena.offset = 0;',
            '    if (!arena.memory) {',
            '        fprintf(stderr, "Arena allocation failed\\n");',
            '        exit(1);',
            '    }',
            '    return arena;',
            '}',
            '',
            'void* arena_alloc(Arena *arena, size_t size) {',
            '    if (arena->offset + size > arena->capacity) {',
            '        fprintf(stderr, "Arena out of memory\\n");',
            '        exit(1);',
            '    }',
            '    void *ptr = arena->memory + arena->offset;',
            '    arena->offset += size;',
            '    return ptr;',
            '}',
            '',
            'void arena_destroy(Arena *arena) {',
            '    free(arena->memory);',
            '    arena->memory = NULL;',
            '    arena->capacity = 0;',
            '    arena->offset = 0;',
            '}',
            '',
            'Arena *global_arena;',
            '',
            '/* Blessed Function Prototypes */',
            'char* join(const char* s1, const char* s2);',
            'double mean(double* data, int n);',
            'double standard_deviation(double* data, int n);',
            'double sample_mean(double* data, int n);',
            'double population_mean(double* data, int n);',
            'double sample_variance(double* data, int n);',
            'double population_variance(double* data, int n);',
            'double sample_std(double* data, int n);',
            'double population_std(double* data, int n);',
            'double median(double* data, int n);',
            'double mode(double* data, int n);',
            'double quantile(double* data, int n, double q);',
            'double iqr(double* data, int n);',
            'double covariance(double* x, double* y, int n);',
            'double correlation(double* x, double* y, int n);',
            'double skewness(double* data, int n);',
            'double kurtosis(double* data, int n);',
            'double t_test(double* x, int n1, double* y, int n2);',
            'double paired_t_test(double* x, double* y, int n);',
            'double chi_square_test(double* observed, double* expected, int n);',
            'double anova_one_way(double* groups, int* sizes, int k);',
            'void mean_confidence_interval(double* data, int n, double alpha, double* lower, double* upper);',
            'void proportion_confidence_interval(int successes, int trials, double alpha, double* lower, double* upper);',
            'double normal_pdf(double x, double mu, double sigma);',
            'double normal_cdf(double x, double mu, double sigma);',
            'double normal_inverse_cdf(double p, double mu, double sigma);',
            'double student_t_cdf(double t, double dof);',
            'double student_t_inverse_cdf(double p, double dof);',
            'double chi_square_cdf(double x, double dof);',
            'double chi_square_inverse_cdf(double p, double dof);',
            'double f_cdf(double x, double dof1, double dof2);',
            'double f_inverse_cdf(double p, double dof1, double dof2);',
            'double sample_normal(double mu, double sigma);',
            'double sample_uniform(double a, double b);',
            'double sample_poisson(double lambda);',
            'void solve_linear_system(double* a, double* b, int n, double* x);',
            'void vector_add(double complex* a, double complex* b, double complex* out, int size);',
            'void vector_sub(double complex* a, double complex* b, double complex* out, int size);',
            'void vector_mul(double complex* a, double complex* b, double complex* out, int size);',
            'void vector_mul_scalar(double complex* a, double complex scalar, double complex* out, int size);',
            'void matrix_multiply(double* a, double* b, int rows_a, int cols_a, int cols_b, double* out);',
            'void invert_matrix(double* a, int n, double* out);',
            'double determinant(double* a, int n);',
            'double trace(double* a, int n);',
            'void transpose(double* a, int rows, int cols, double* out);',
            'void eigenvalues(double* a, int n, double* real_parts, double* imag_parts);',
            'void eigenvectors(double* a, int n, double* vecs);',
            'void lu_decompose(double* a, int n, double* l, double* u);',
            'void qr_decompose(double* a, int rows, int cols, double* q, double* r);',
            'void svd(double* a, int rows, int cols, double* u, double* s, double* vt);',
            'double vector_norm(double* x, int n);',
            'double matrix_norm(double* a, int rows, int cols);',
            'double condition_number(double* a, int n);',
        ]))

        for fn in self.functions:
            parts.append(fn)

        main_lines = [
            'int main(void)',
            '{',
            '    Arena arena = arena_create(16 * 1024 * 1024);',
            '    global_arena = &arena;',
        ]
        for line in self.global_inits:
            main_lines.append(f'    {line}')
        main_lines.extend(self.main_body)
        main_lines.extend(['    arena_destroy(&arena);', '    return 0;', '}'])

        parts.append('\n'.join(main_lines))
        return '\n\n'.join(parts) + '\n'


# ===========================================================================
# 9.  PUBLIC API
# ===========================================================================

def compile_veritas(source: str) -> str:
    """Full pipeline: Veritas source → C source."""
    src = strip_comments(source)
    parser = Parser()
    for stmt in logical_lines(src):
        parser.feed(stmt)
    gen = CodeGen()
    return gen.generate(parser.ast())


# ===========================================================================
# 10.  CLI ENTRY POINT
# ===========================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 vcparser.py <source.ver>', file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as fh:
        print(compile_veritas(fh.read()))
