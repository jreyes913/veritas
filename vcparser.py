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
    Warns if the wrong article is used; output is unaffected either way.
    """
    t = t.strip()
    if t == 'nothing':
        return 'void'
    m = re.match(r'^(an?)\s+(.+)', t, re.IGNORECASE)
    if m:
        article, ctype = m.group(1).lower(), m.group(2)
        if ctype[0].lower() in 'aeiou' and article != 'an':
            print(f"Warning: '{ctype}' starts with a vowel, expected 'an'")
        elif ctype[0].lower() not in 'aeiou' and article != 'a':
            print(f"Warning: '{ctype}' starts with a consonant, expected 'a'")
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

    m = re.match(r"an element of '(\w+)' at index '(\w+)'", token)
    if m:
        return f'{m.group(1)}[{m.group(2)}]'

    m = re.match(r"value at '(\w+)'", token)
    if m:
        return f'*{m.group(1)}'

    m = re.match(r"the address of '(\w+)'", token)
    if m:
        return f'&{m.group(1)}'

    if token.startswith("'") and token.endswith("'") and len(token) > 2:
        return token[1:-1]

    return token


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
            return (
                f'{_translate_simple(lhs, allow_chained=True)}'
                f' {best_cop} '
                f'{_translate_inner(rhs)}'
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
            return f'{translate_value(lhs)} {cop} {translate_value(rhs)}'
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

        parts: list[str] = []
        for i, clause in enumerate(clauses):
            op, core = _parse_quantity_clause(clause)
            c_group = _translate_quantity(core)
            if i == 0:
                parts.append(c_group)
            else:
                if op is None:
                    parts.append(
                        f'/* ERROR: missing operator before clause '
                        f'{i + 1}: {clause} */ {c_group}'
                    )
                else:
                    parts.append(f' {op} {c_group}')

        return ''.join(parts)

    return _translate_simple(expr)


def translate_condition(cond: str) -> str:
    """Translate a Veritas comparison condition to a C boolean expression."""
    cond = cond.strip().rstrip(':')
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
    Parse a comma / 'and'-separated Veritas argument list.
    Handles two-item 'A and B' and three-or-more 'A, B, and C' forms.
    """
    raw_p = _protect(raw)
    parts = [p.strip() for p in raw_p.split(',')]
    result: list[str] = []
    for part in parts:
        part = re.sub(r'^and\s+', '', part, flags=re.IGNORECASE).strip()
        part = _unprotect(part).strip()
        if part:
            result.append(part)

    if len(result) == 1 and result[0]:
        and_parts = re.split(r'\band\b', _protect(raw), maxsplit=1)
        if len(and_parts) == 2:
            a = _unprotect(and_parts[0]).strip()
            b = _unprotect(and_parts[1]).strip()
            if a and b:
                return [a, b]

    return result


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

    def feed(self, stmt: str) -> None:
        s = strip_terminal_period(stmt.strip())
        self._dispatch(s)

    def ast(self) -> ASTNode:
        return self._module

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

        m = re.match(r"Replace (.+?) with (.+)$", s)
        if m:
            self._current_scope().append({
                'kind':   'assign',
                'target': translate_value(m.group(1)),
                'value':  translate_expression(m.group(2)),
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
        self._pop_scope()
        assert self._current_func is not None
        self._module['functions'].append(self._current_func)
        self._current_func = None
        self._in_function = False

    def _handle_create(self, s: str) -> None:
        node: Optional[ASTNode] = None

        m = re.match(
            r"Create '(\w+)' as an?\s+([\w ]+?) array of size (\d+) with values:(.+)$",
            s, re.DOTALL)
        if m:
            name, base, size, vals_raw = m.groups()
            vals = [
                re.sub(r'^and\s+', '', v.strip(), flags=re.IGNORECASE).strip()
                for v in vals_raw.split(',') if v.strip()
            ]
            node = {'kind': 'declare', 'ctype': map_type(base), 'name': name,
                    'is_array': True, 'size': int(size), 'init': vals}

        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+([\w ]+?) array of size (\d+)", s)
            if m:
                node = {'kind': 'declare', 'ctype': map_type(m.group(2)),
                        'name': m.group(1), 'is_array': True,
                        'size': int(m.group(3)), 'init': None}

        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+(.+?) with value (.+)$", s)
            if m:
                node = {'kind': 'declare', 'ctype': map_type(m.group(2).strip()),
                        'name': m.group(1), 'is_array': False, 'size': None,
                        'init': translate_expression(m.group(3).strip())}

        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+(.+)$", s)
            if m:
                node = {'kind': 'declare', 'ctype': map_type(m.group(2).strip()),
                        'name': m.group(1), 'is_array': False,
                        'size': None, 'init': None}

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
        self._pop_scope()
        if_node = self._block_stack[-1]
        assert if_node['kind'] == 'if', "Otherwise without If"
        self._push_scope(if_node['else_body'])

    def _end_if(self) -> None:
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

    def __init__(self) -> None:
        self.includes:  list[str] = []
        self.globals:   list[str] = []
        self.functions: list[str] = []
        self.main_body: list[str] = []

    def generate(self, module: ASTNode) -> str:
        self._gen_includes(module['includes'])
        self._gen_globals(module['globals'])
        self._gen_functions(module['functions'])
        self._gen_main(module['main'])
        return self._render()

    def _gen_includes(self, nodes: list[ASTNode]) -> None:
        for node in nodes:
            self.includes.append(f'#include <{node["path"]}>')

    def _gen_globals(self, nodes: list[ASTNode]) -> None:
        for node in nodes:
            self.globals.append(self._decl_c(node))

    def _gen_functions(self, nodes: list[ASTNode]) -> None:
        for func in nodes:
            self.functions.append('\n'.join(self._func_c(func)))

    def _gen_main(self, nodes: list[ASTNode]) -> None:
        for node in nodes:
            for line in self._node_c(node, indent=1):
                self.main_body.append(line)

    def _node_c(self, node: ASTNode, indent: int) -> list[str]:
        pad  = '    ' * indent
        kind = node['kind']

        if kind == 'declare':
            return [pad + self._decl_c(node)]

        if kind == 'assign':
            return [f'{pad}{node["target"]} = {node["value"]};']

        if kind == 'call':
            args_str = ', '.join(node['args'])
            call     = f'{node["func"]}({args_str})'
            if node['dest'] is None:
                return [f'{pad}{call};']
            return [f'{pad}{node["dest"]} = {call};']

        if kind == 'for':
            op  = '<=' if node['inclusive'] else '<'
            var = node['var']
            lines = [
                f'{pad}for (int {var} = {node["start"]}; '
                f'{var} {op} {node["end"]}; {var}++) {{'
            ]
            for child in node['body']:
                lines.extend(self._node_c(child, indent + 1))
            lines.append(pad + '}')
            return lines

        if kind == 'if':
            lines = [f'{pad}if ({node["condition"]}) {{']
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

    def _decl_c(self, node: ASTNode) -> str:
        ctype = node['ctype']
        name  = node['name']
        if node['is_array']:
            size = node['size']
            if node['init']:
                vals = ', '.join(node['init'])
                return f'{ctype} {name}[{size}] = {{{vals}}};'
            return f'{ctype} {name}[{size}];'
        if node['init'] is not None:
            return f'{ctype} {name} = {node["init"]};'
        return f'{ctype} {name};'

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
        for child in func['body']:
            lines.extend(self._node_c(child, indent=1))
        lines.append('}')
        return lines

    def _render(self) -> str:
        parts: list[str] = []
        if self.includes:
            parts.append('\n'.join(self.includes))
        if self.globals:
            parts.append('\n'.join(self.globals))
        for fn in self.functions:
            parts.append(fn)
        parts.append(
            '\n'.join(['int main(void)', '{'] + self.main_body + ['}'])
        )
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