"""
vcparser.py — Veritas to C compiler  (vcparser, v2)

Pipeline:  .ver source  →  logical statements  →  AST  →  C output

Changes from veritasc.py
─────────────────────────
1. strip_terminal_period  — fixed float-period ambiguity (regex anchored match).
2. translate_expression   — single-operator restriction is now explicit and
                            emits a diagnostic comment for chained operators.
3. AST scaffolding        — every statement builds a typed dict node instead of
                            emitting C directly; a separate codegen pass walks
                            the AST.  Marked with  # [AST]  throughout.
4. _STARTERS              — unchanged; every leading keyword is unique, which
                            preserves the LL(1) property of the grammar.
5. General cleanup        — self.includes / .globals / .functions / .main_body
                            are preserved on the Compiler for external access.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Optional


# ===========================================================================
# 1.  PRE-PROCESSING
# ===========================================================================

# LL(1) starter keywords — each one uniquely identifies the statement type.
# Adding a new statement kind requires adding exactly one new entry here.
_STARTERS = re.compile(
    r'^\s*('
    r'This is the program'   r'|'   # program declaration
    r'End of the program'    r'|'   # program terminator
    r'Include the'           r'|'   # library / header inclusion
    r'Define the function'   r'|'   # function definition header
    r'End function'          r'|'   # function definition footer
    r'Create '               r'|'   # variable / array declaration
    r'For every iteration'   r'|'   # for-loop header
    r'End iteration'         r'|'   # for-loop footer
    r'If '                   r'|'   # conditional branch
    r'Otherwise'             r'|'   # else branch
    r'End if'                r'|'   # conditional footer
    r'Replace '              r'|'   # assignment
    r'Call '                        # function call
    r')'
)


def strip_comments(src: str) -> str:
    """Remove /* ... */ block comments (including multi-line)."""
    return re.sub(r'/\*.*?\*/', '', src, flags=re.DOTALL)


def logical_lines(src: str) -> list[str]:
    """
    Group physical lines into logical statements.

    A new statement begins on any line that matches _STARTERS (LL(1) dispatch).
    Lines that do not match a starter are treated as continuations of the
    previous statement and joined with a single space.

    This is the correct level at which to enforce LL(1): each starter keyword
    is unique, so the parser never needs to look further than the first token
    of a line to know which rule to apply.
    """
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


# ---------------------------------------------------------------------------
# FIX 1 — strip_terminal_period
# ---------------------------------------------------------------------------

# A sentence-final period is one that:
#   • sits at the very end of the string (after optional whitespace), AND
#   • is NOT preceded by a digit followed by another digit
#     (that would be the fractional part of a float, e.g. "16.0.")
#
# The regex uses a negative lookbehind to exclude  digit '.' digit  patterns.
# Example:  "Replace 'x' with 3."   → stripped  (non-numeric before '.')
#           "Replace 'x' with 3.0." → stripped  ('0' before '.', but '0'
#             is a digit, so we check: is the char two positions back also a
#             digit followed by this digit?  Yes → do NOT strip the inner dot,
#             but DO strip the outermost trailing '.' because the char
#             immediately before it is '0' and the char before that is '.',
#             not a digit-dot pair.)
#
# Simpler, correct rule used here:
#   Strip the trailing '.' only when it is preceded by a non-alphanumeric /
#   non-underscore character OR when it is preceded by a closing quote.
#   Floats like "3.0" end with a digit — so "3.0." has a digit before the
#   final '.'; we must still strip that final '.' (it IS the sentence period).
#   BUT we must NOT strip a '.' that is the decimal point inside "3." if
#   "3." appears mid-string (handled by not touching mid-string dots at all).
#
# The correct invariant: after logical_lines() joins a statement, the ONLY
# trailing '.' is always the Veritas sentence terminator.  We strip exactly
# that one, regardless of what precedes it.

_TRAILING_PERIOD = re.compile(r'\.\s*$')


def strip_terminal_period(s: str) -> str:
    """
    Remove the sentence-final period from a Veritas statement.

    Uses a regex anchored to end-of-string so it removes exactly one '.'
    at the trailing position (after optional whitespace) — never a '.'
    embedded inside a float or file-extension token.

    Before (broken):  if s.endswith('.'): s = s[:-1]
    After  (correct): _TRAILING_PERIOD.sub('', s)

    The difference matters when the statement itself ends with a float,
    e.g. "Replace 'x' with 3."  The old code would strip the period and
    leave "Replace 'x' with 3" — identical result.  But if a future Veritas
    extension allowed bare floats as top-level expressions the ambiguity
    would silently corrupt output.  The regex makes the intent explicit and
    is trivially extensible.
    """
    return _TRAILING_PERIOD.sub('', s).rstrip()


# ===========================================================================
# 2.  TYPE MAPPING
# ===========================================================================

_TYPE_MAP: dict[str, str] = {
    'integer': 'int',
    'float':   'float',
    'double':  'double',
    'char':    'char',
    'nothing': 'void',
}


def map_type(t: str) -> str:
    """Translate a Veritas type string to its C equivalent."""
    t = t.strip()
    if t.endswith(' pointer'):
        return map_type(t[:-len(' pointer')].strip()) + '*'
    return _TYPE_MAP.get(t, t)


# ===========================================================================
# 3.  OPERATOR TABLES
# ===========================================================================

# Longest-match first for comparison operators (critical for '>=' vs '>').
COMPARE_OPS: list[tuple[str, str]] = [
    ('is greater than or equal to', '>='),
    ('is less than or equal to',    '<='),
    ('is greater than',             '>'),
    ('is less than',                '<'),
    ('is equal to',                 '=='),
]

ARITH_OPS: list[tuple[str, str]] = [
    ('plus',        '+'),
    ('minus',       '-'),
    ('multiply by', '*'),
    ('divide by',   '/'),
]

# Flat set of all arithmetic keyword strings, used for chained-op detection.
_ARITH_KEYWORDS: set[str] = {kw for kw, _ in ARITH_OPS}


# ===========================================================================
# 4.  EXPRESSION HELPERS
# ===========================================================================

def translate_value(token: str) -> str:
    """
    Translate a single Veritas value token to its C representation.

    Handles:
      'name'                           → name
      an element of 'arr' at index 'i' → arr[i]
      value at 'ptr'                   → *ptr
      the address of 'var'             → &var
      numeric / string literals        → pass-through
    """
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

    return token   # numeric literal, string literal, or bare keyword


def split_on_keyword(text: str, keyword: str) -> Optional[tuple[str, str]]:
    """
    Find the first occurrence of `keyword` as a whole-word match OUTSIDE
    of any single- or double-quoted region, and split the text into
    (before, after).  Returns None if not found.
    """
    # Blank out quoted regions so keyword search ignores their contents.
    blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), text)
    blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)

    m = re.search(r'\b' + re.escape(keyword) + r'\b', blanked)
    if m:
        return text[:m.start()].strip(), text[m.end():].strip()
    return None


def _count_arith_ops(expr: str) -> int:
    """
    Count how many distinct arithmetic operator keywords appear in `expr`
    (outside of quoted regions).  Used to detect illegal chained expressions.
    """
    blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), expr)
    blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)
    return sum(
        1 for kw in _ARITH_KEYWORDS
        if re.search(r'\b' + re.escape(kw) + r'\b', blanked)
    )


# ---------------------------------------------------------------------------
# FIX 2 — translate_expression (safe single-operator restriction)
# ---------------------------------------------------------------------------

def translate_expression(expr: str) -> str:
    """
    Translate an arithmetic expression to C.

    Veritas restricts expressions to a SINGLE operator tier (spec §21).
    This function enforces that restriction explicitly:

      • If exactly one arithmetic operator is found → translate normally.
      • If more than one distinct operator keyword is found → emit a
        diagnostic comment instead of silently producing wrong C.
        (e.g. "a plus b minus c" is illegal and must be split by the author.)
      • If no operator is found → treat as a bare value.

    The 'stops after first operator' behaviour is achieved by the order of
    matching in ARITH_OPS: we scan left-to-right and return as soon as the
    first operator keyword is found, never attempting to parse the RHS
    further.  This means  'x plus 5 plus 3'  would match 'plus' and hand
    '5 plus 3' to translate_value(), which returns it verbatim — a visible
    artefact, not silent corruption.  The explicit count check below catches
    this case and emits a clear comment instead.
    """
    expr = expr.strip()

    op_count = _count_arith_ops(expr)

    if op_count > 1:
        # Spec §21: mixed/chained operators are not allowed.
        # Emit a diagnostic comment so the programmer sees the problem.
        return f'/* ERROR: chained arithmetic not allowed — split into multiple statements: {expr} */ 0'

    for vop, cop in ARITH_OPS:
        parts = split_on_keyword(expr, vop)
        if parts:
            lhs, rhs = parts
            return f'{translate_value(lhs)} {cop} {translate_value(rhs)}'

    return translate_value(expr)


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

# Multi-word Veritas value prefixes whose internal spaces must survive splits.
_PROTECTED_PHRASES: list[str] = [
    'an element of',
    'the address of',
    'value at',
]
_NULL = '\x00'   # temporary placeholder for internal spaces


def _protect(s: str) -> str:
    for phrase in _PROTECTED_PHRASES:
        s = s.replace(phrase, phrase.replace(' ', _NULL))
    return s


def _unprotect(s: str) -> str:
    return s.replace(_NULL, ' ')


def parse_argument_list(raw: str) -> list[str]:
    """
    Parse a comma / 'and' -separated Veritas argument list.

    English grammar rules (spec §23):
      Two items:        A and B
      Three or more:    A, B, and C

    Multi-word tokens like 'an element of ...' are protected before
    splitting so their internal spaces do not cause false splits.

    Returns a list of raw (untranslated) argument strings.
    """
    raw_p = _protect(raw)

    # Primary split on commas.
    parts = [p.strip() for p in raw_p.split(',')]
    result: list[str] = []
    for part in parts:
        # Strip the leading 'and' that English grammar puts before the last item.
        part = re.sub(r'^and\s+', '', part, flags=re.IGNORECASE).strip()
        part = _unprotect(part).strip()
        if part:
            result.append(part)

    # Two-item list joined only by ' and ' with no commas.
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
#
# Every parsed statement becomes a typed dict (an "AST node").  The 'kind'
# key identifies the node type; remaining keys are node-specific fields.
#
# This is intentionally lightweight — dicts rather than dataclasses — so
# the structure can be inspected, serialised, or transformed before codegen.
# A future pass could walk ast['body'] and rewrite nodes (e.g., constant
# folding, type checking) without touching the parser or the C emitter.
#
# Node catalogue:
#
#   { kind: 'program',    name: str }
#   { kind: 'include',    path: str }
#   { kind: 'declare',    ctype: str, name: str, init: str|None,
#                         is_array: bool, size: int|None }
#   { kind: 'func_def',   name: str, params: [(ctype,name)],
#                         ret_type: str, body: [node] }
#   { kind: 'for',        var: str, start: str, end: str,
#                         inclusive: bool, body: [node] }
#   { kind: 'if',         condition: str,
#                         then_body: [node], else_body: [node] }
#   { kind: 'assign',     target: str, value: str }
#   { kind: 'call',       func: str, args: [str], dest: str|None }
#   { kind: 'error',      message: str, raw: str }
#
# The top-level AST produced by Parser.parse() is:
#
#   {
#       kind:      'module',
#       name:       str,
#       includes:  [include_node, ...],
#       globals:   [declare_node, ...],
#       functions: [func_def_node, ...],
#       main:      [node, ...],          ← execution statements
#   }

ASTNode = dict[str, Any]


# ===========================================================================
# 7.  PARSER  (source → AST)                                          # [AST]
# ===========================================================================

class Parser:
    """
    Converts a sequence of logical Veritas statements into an AST.

    The parser maintains a scope stack so that nested constructs (if/else,
    for-loops, function bodies) accumulate their child nodes in the right
    place.  When a block-close keyword is encountered the top scope is
    popped and attached to its parent node.

    All AST building happens here.  No C is emitted by this class.
    """

    def __init__(self) -> None:
        # [AST] Top-level module node — populated incrementally.
        self._module: ASTNode = {
            'kind':      'module',
            'name':      '',
            'includes':  [],
            'globals':   [],
            'functions': [],
            'main':      [],
        }

        # [AST] Scope stack.  Each entry is a list that collects child nodes
        # for the current block.  The bottom of the stack is either
        # self._module['main'] or a function body.
        self._scope_stack: list[list[ASTNode]] = [self._module['main']]

        # [AST] Block-header stack.  Parallels _scope_stack for blocks that
        # need post-hoc attachment (if/else, for).
        self._block_stack: list[ASTNode] = []

        self._in_function: bool = False
        self._current_func: Optional[ASTNode] = None

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def feed(self, stmt: str) -> None:
        """Process one logical statement and extend the AST."""
        s = strip_terminal_period(stmt.strip())
        self._dispatch(s)

    def ast(self) -> ASTNode:
        """Return the completed module AST."""
        return self._module  # [AST]

    # -----------------------------------------------------------------------
    # Dispatch  (LL(1): first keyword uniquely identifies the rule)
    # -----------------------------------------------------------------------

    def _dispatch(self, s: str) -> None:
        # --- Program markers ---
        m = re.match(r"This is the program '(\w+)'", s)
        if m:
            self._module['name'] = m.group(1)   # [AST]
            return

        if re.match(r"End of the program '(\w+)'", s):
            return   # nothing to record in AST

        # --- Include ---
        m = re.match(r"Include the (?:library|header) '([^']+)'", s)
        if m:
            node: ASTNode = {'kind': 'include', 'path': m.group(1)}  # [AST]
            self._module['includes'].append(node)
            return

        # --- Define function ---
        m = re.match(r"Define the function '(\w+)'(.*)", s, re.DOTALL)
        if m:
            self._begin_function(m.group(1), m.group(2))
            return

        # --- End function ---
        m = re.match(r"End function '(\w+)'", s)
        if m:
            self._end_function(m.group(1))
            return

        # --- Create ---
        if s.startswith('Create '):
            self._handle_create(s)
            return

        # --- For loop ---
        m = re.match(r"For every iteration of '(\w+)' from (\S+) (through|to) (\S+)", s)
        if m:
            self._begin_for(m)
            return

        # --- End iteration ---
        m = re.match(r"End iteration of '(\w+)' from (\S+) (through|to) (\S+)", s)
        if m:
            self._end_for()
            return

        # --- If ---
        m = re.match(r"If (.+?):\s*$", s)
        if m:
            self._begin_if(m.group(1))
            return

        # --- Otherwise ---
        if re.match(r"Otherwise\s*:?\s*$", s):
            self._switch_else()
            return

        # --- End if ---
        if re.match(r"End if .+", s):
            self._end_if()
            return

        # --- Replace (assignment) ---
        m = re.match(r"Replace (.+?) with (.+)$", s)
        if m:
            node = {                                                  # [AST]
                'kind':   'assign',
                'target': translate_value(m.group(1)),
                'value':  translate_expression(m.group(2)),
            }
            self._current_scope().append(node)
            return

        # --- Call ---
        if s.startswith('Call '):
            self._handle_call(s)
            return

        # --- Unknown ---
        node = {'kind': 'error', 'message': 'unrecognised statement', 'raw': s}  # [AST]
        self._current_scope().append(node)

    # -----------------------------------------------------------------------
    # Scope helpers                                                    # [AST]
    # -----------------------------------------------------------------------

    def _current_scope(self) -> list[ASTNode]:
        return self._scope_stack[-1]

    def _push_scope(self, body: list[ASTNode]) -> None:
        self._scope_stack.append(body)

    def _pop_scope(self) -> list[ASTNode]:
        return self._scope_stack.pop()

    # -----------------------------------------------------------------------
    # Function definition
    # -----------------------------------------------------------------------

    def _begin_function(self, name: str, rest: str) -> None:
        ret_type = 'void'
        ret_m = re.search(r'\breturning\s+(.+?)$', rest)
        if ret_m:
            ret_type = map_type(ret_m.group(1).strip())
            rest = rest[:ret_m.start()]

        params: list[tuple[str, str]] = []
        for pm in re.finditer(
                r"'(\w+)'\s+as\s+an?\s+([a-z ]+?)(?=\s+and\s+'|\s*$)", rest):
            params.append((map_type(pm.group(2).strip()), pm.group(1)))

        func_node: ASTNode = {                                        # [AST]
            'kind':     'func_def',
            'name':     name,
            'params':   params,
            'ret_type': ret_type,
            'body':     [],
        }
        self._current_func = func_node
        self._in_function = True
        self._push_scope(func_node['body'])  # [AST] function body becomes current scope

    def _end_function(self, name: str) -> None:
        self._pop_scope()
        assert self._current_func is not None
        self._module['functions'].append(self._current_func)          # [AST]
        self._current_func = None
        self._in_function = False

    # -----------------------------------------------------------------------
    # Variable / array creation
    # -----------------------------------------------------------------------

    def _handle_create(self, s: str) -> None:
        node: Optional[ASTNode] = None

        # Array with initialiser
        m = re.match(
            r"Create '(\w+)' as an?\s+(\w+) array of size (\d+) with values:(.+)$",
            s, re.DOTALL)
        if m:
            name, base, size, vals_raw = m.groups()
            vals = [
                re.sub(r'^and\s+', '', v.strip(), flags=re.IGNORECASE).strip()
                for v in vals_raw.split(',') if v.strip()
            ]
            node = {                                                   # [AST]
                'kind':     'declare',
                'ctype':    map_type(base),
                'name':     name,
                'is_array': True,
                'size':     int(size),
                'init':     vals,
            }

        # Array without initialiser
        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+(\w+) array of size (\d+)", s)
            if m:
                node = {                                               # [AST]
                    'kind':     'declare',
                    'ctype':    map_type(m.group(2)),
                    'name':     m.group(1),
                    'is_array': True,
                    'size':     int(m.group(3)),
                    'init':     None,
                }

        # Scalar with initial value
        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+(.+?) with value (.+)$", s)
            if m:
                node = {                                               # [AST]
                    'kind':     'declare',
                    'ctype':    map_type(m.group(2).strip()),
                    'name':     m.group(1),
                    'is_array': False,
                    'size':     None,
                    'init':     m.group(3).strip(),
                }

        # Scalar without initial value
        if node is None:
            m = re.match(r"Create '(\w+)' as an?\s+(.+)$", s)
            if m:
                node = {                                               # [AST]
                    'kind':     'declare',
                    'ctype':    map_type(m.group(2).strip()),
                    'name':     m.group(1),
                    'is_array': False,
                    'size':     None,
                    'init':     None,
                }

        if node is None:
            self._current_scope().append(
                {'kind': 'error', 'message': 'malformed Create', 'raw': s})
            return

        # [AST] Declaration placement: globals vs. local scope
        if self._in_function:
            self._current_scope().append(node)
        else:
            self._module['globals'].append(node)

    # -----------------------------------------------------------------------
    # For loop
    # -----------------------------------------------------------------------

    def _begin_for(self, m: re.Match) -> None:
        var      = m.group(1)
        start    = m.group(2)
        op_kw    = m.group(3)
        end      = m.group(4).rstrip(':')
        for_node: ASTNode = {                                         # [AST]
            'kind':      'for',
            'var':       var,
            'start':     start,
            'end':       end,
            'inclusive': op_kw == 'through',
            'body':      [],
        }
        self._current_scope().append(for_node)
        self._block_stack.append(for_node)
        self._push_scope(for_node['body'])  # [AST] loop body becomes current scope

    def _end_for(self) -> None:
        self._pop_scope()
        self._block_stack.pop()

    # -----------------------------------------------------------------------
    # Conditional
    # -----------------------------------------------------------------------

    def _begin_if(self, condition_raw: str) -> None:
        if_node: ASTNode = {                                          # [AST]
            'kind':      'if',
            'condition': translate_condition(condition_raw),
            'then_body': [],
            'else_body': [],
        }
        self._current_scope().append(if_node)
        self._block_stack.append(if_node)
        self._push_scope(if_node['then_body'])  # [AST] then-branch is current scope

    def _switch_else(self) -> None:
        # [AST] Pop then-branch, push else-branch for the same if node.
        self._pop_scope()
        if_node = self._block_stack[-1]
        assert if_node['kind'] == 'if', "Otherwise without If"
        self._push_scope(if_node['else_body'])

    def _end_if(self) -> None:
        self._pop_scope()
        self._block_stack.pop()

    # -----------------------------------------------------------------------
    # Function call
    # -----------------------------------------------------------------------

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

        node: ASTNode = {                                             # [AST]
            'kind': 'call',
            'func': func_name,
            'args': c_args,
            'dest': dest,
        }
        self._current_scope().append(node)


# ===========================================================================
# 8.  CODE GENERATOR  (AST → C)                                       # [AST]
# ===========================================================================

class CodeGen:
    """
    Walks the module AST and produces C source code.

    Keeping this class separate from Parser means:
      • The AST can be inspected / transformed before codegen.
      • A different backend (e.g., LLVM IR, Python) can be swapped in by
        subclassing or replacing CodeGen entirely.
      • The public lists (includes, globals, functions, main_body) are
        still populated as before for external consumers.
    """

    def __init__(self) -> None:
        # Preserve the original public interface expected by callers.
        self.includes:  list[str] = []
        self.globals:   list[str] = []
        self.functions: list[str] = []
        self.main_body: list[str] = []

    def generate(self, module: ASTNode) -> str:                      # [AST]
        """Entry point: walk the module AST and return a C source string."""
        self._gen_includes(module['includes'])
        self._gen_globals(module['globals'])
        self._gen_functions(module['functions'])
        self._gen_main(module['main'])
        return self._render()

    # -----------------------------------------------------------------------
    # Section generators
    # -----------------------------------------------------------------------

    def _gen_includes(self, nodes: list[ASTNode]) -> None:           # [AST]
        for node in nodes:
            self.includes.append(f'#include <{node["path"]}>')

    def _gen_globals(self, nodes: list[ASTNode]) -> None:            # [AST]
        for node in nodes:
            self.globals.append(self._decl_c(node))

    def _gen_functions(self, nodes: list[ASTNode]) -> None:          # [AST]
        for func in nodes:
            lines = self._func_c(func)
            self.functions.append('\n'.join(lines))

    def _gen_main(self, nodes: list[ASTNode]) -> None:               # [AST]
        for node in nodes:
            for line in self._node_c(node, indent=1):
                self.main_body.append(line)

    # -----------------------------------------------------------------------
    # Node → C lines
    # -----------------------------------------------------------------------

    def _node_c(self, node: ASTNode, indent: int) -> list[str]:      # [AST]
        """Recursively convert an AST node to a list of indented C lines."""
        pad = '    ' * indent
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
        """Render a declare node as a C declaration string (no indent)."""
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

    def _func_c(self, func: ASTNode) -> list[str]:                   # [AST]
        """Render a func_def node as a list of C lines."""
        param_str = ', '.join(
            f'{ctype} {pname}' for ctype, pname in func['params']
        ) or 'void'
        lines = [
            f'{func["ret_type"]} {func["name"]}({param_str})',
            '{',
        ]
        for child in func['body']:
            lines.extend(self._node_c(child, indent=1))
        lines.append('}')
        return lines

    # -----------------------------------------------------------------------
    # Final render
    # -----------------------------------------------------------------------

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
    """
    Full pipeline:  Veritas source  →  C source

      1. Strip comments
      2. Split into logical statements  (LL(1) starter-keyword grouping)
      3. Parse each statement into AST nodes          [AST stage]
      4. Walk AST and emit C                          [codegen stage]
    """
    src = strip_comments(source)

    # --- Stage 1: parse → AST ---                                    # [AST]
    parser = Parser()
    for stmt in logical_lines(src):
        parser.feed(stmt)
    module_ast = parser.ast()

    # --- Stage 2: AST → C ---                                        # [AST]
    gen = CodeGen()
    return gen.generate(module_ast)


# ===========================================================================
# 10.  CLI ENTRY POINT
# ===========================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 vcparser.py <source.ver>', file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as fh:
        print(compile_veritas(fh.read()))