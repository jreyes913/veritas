from __future__ import annotations

import re

from compiler.semantic.symbol_table import SymbolTable


class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    BLESSED_FUNCTIONS = {
        # Strings
        'join': 'string',
        'substring': 'string',
        'to_uppercase': 'string',
        'to_lowercase': 'string',
        'regex_search': 'int',
        'regex_replace': 'string',
        # Stats
        'mean': 'double',
        'standard_deviation': 'double',
        # Linear Algebra
        'solve_linear_system': 'void',
        'matrix_multiply': 'void',
        'invert_matrix': 'void',
        # Signal Processing
        'fft_forward': 'void',
        'fft_backward': 'void',
    }

    def __init__(self) -> None:
        self.symbols = SymbolTable()
        self._scope_stack: list[dict[str, str]] = [dict()]
        for func, ret in self.BLESSED_FUNCTIONS.items():
            # Define blessed functions in a separate way or just skip lookup for them
            pass

    def analyze(self, ast_program: dict) -> SymbolTable:
        for glob in ast_program.get('globals', []):
            self._handle_declare(glob, 'global')

        for func in ast_program.get('functions', []):
            self._analyze_function(func)

        self._analyze_nodes(ast_program.get('main', []), 'main')
        return self.symbols

    def _lookup(self, name: str) -> str | None:
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        return None

    def _define(self, name: str, ctype: str, scope: str) -> None:
        self._scope_stack[-1][name] = ctype
        self.symbols.define(name, ctype, scope)

    def _push_scope(self) -> None:
        self._scope_stack.append(dict())

    def _pop_scope(self) -> None:
        self._scope_stack.pop()

    def _analyze_function(self, func: dict) -> None:
        fn_name = func['name']
        self._push_scope()
        for ctype, name in func.get('params', []):
            self._define(name, ctype, f'param:{fn_name}')
        self._analyze_nodes(func.get('body', []), f'func:{fn_name}')
        self._pop_scope()

    def _analyze_nodes(self, nodes: list[dict], scope: str) -> None:
        for node in nodes:
            kind = node.get('kind')
            if kind == 'declare':
                self._handle_declare(node, scope)
            elif kind == 'assign':
                self._handle_assign(node)
            elif kind == 'call':
                self._handle_call(node)
            elif kind == 'if':
                self._infer_expr_type(node.get('condition', ''), context='if condition')
                self._push_scope()
                self._analyze_nodes(node.get('then_body', []), scope)
                self._pop_scope()
                self._push_scope()
                self._analyze_nodes(node.get('else_body', []), scope)
                self._pop_scope()
            elif kind == 'for':
                self._push_scope()
                self._define(node['var'], 'int', f'loop:{scope}')
                self._infer_expr_type(str(node.get('start', '')), context='for start')
                self._infer_expr_type(str(node.get('end', '')), context='for end')
                self._analyze_nodes(node.get('body', []), scope)
                self._pop_scope()
            elif kind == 'error':
                raise SemanticError(f"Parser error: {node.get('message')} ({node.get('raw')})")

    def _handle_declare(self, node: dict, scope: str) -> None:
        name = node['name']
        ctype = node['ctype']
        self._define(name, ctype, scope)

        init = node.get('init')
        if node.get('is_array'):
            if init:
                for value in init:
                    value_type = self._infer_expr_type(value, context=f"initializer for '{name}'")
                    self._assert_assignable(ctype, value_type, f"initializer for '{name}'")
            return

        if init is not None:
            value_type = self._infer_expr_type(init, context=f"initializer for '{name}'")
            self._assert_assignable(ctype, value_type, f"initializer for '{name}'")

    def _handle_assign(self, node: dict) -> None:
        target = node['target']
        target_type = self._infer_target_type(target)
        value_type = self._infer_expr_type(node['value'], context=f"assignment to '{target}'")
        self._assert_assignable(target_type, value_type, f"assignment to '{target}'")

    def _handle_call(self, node: dict) -> None:
        func_name = node['func']
        
        for arg in node.get('args', []):
            arg = arg.strip()
            # If the parser didn't perfectly clean 'and' in some cases
            if arg.lower().startswith('and '):
                arg = arg[4:].strip()
            self._infer_expr_type(arg, context=f"argument to '{func_name}'")
        
        dest = node.get('dest')
        if dest is not None:
            dest_type = self._infer_target_type(dest)
            
            # Check if it's a blessed function
            if func_name in self.BLESSED_FUNCTIONS:
                ret_type = self.BLESSED_FUNCTIONS[func_name]
                if ret_type != 'void':
                    self._assert_assignable(dest_type, ret_type, f"result of '{func_name}'")

    def _infer_target_type(self, target: str) -> str:
        target = target.strip()
        if target.startswith('*'):
            ptr_name = target[1:].strip()
            ctype = self._lookup(ptr_name)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{ptr_name}'")
            if not ctype.endswith('*'):
                raise SemanticError(f"Cannot dereference non-pointer '{ptr_name}'")
            return ctype[:-1].strip() or 'void'

        if '[' in target and target.endswith(']'):
            base = target.split('[', 1)[0].strip()
            ctype = self._lookup(base)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{base}'")
            if ctype.endswith('*'):
                return ctype[:-1].strip() or 'void'
            return ctype

        ctype = self._lookup(target)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{target}'")
        return ctype

    def _infer_expr_type(self, expr: str, context: str = 'expression') -> str:
        expr = expr.strip()
        if not expr:
            return 'void'

        if expr.lower().startswith('the quantity '):
            return self._infer_expr_type(expr[len('the quantity '):].strip(), context=context)

        if expr.startswith('strcmp(') and expr.endswith(')') or 'strcmp(' in expr:
            return 'int'
        
        if expr == '_Complex_I' or re.fullmatch(r'(\d+\.?\d*|\.\d+)j', expr):
            return 'double complex'

        if expr.startswith('"') or expr.endswith('"'):
            # Basic fallback for strings that might have been mangled or have escaped chars
            return 'string'

        if expr.startswith("'") and expr.endswith("'"):
            name = expr[1:-1]
            ctype = self._lookup(name)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{expr}'")
            return ctype

        while expr.startswith('(') and expr.endswith(')'):
            # Only strip if it's a matching pair of outermost parens
            depth = 0
            balanced = True
            for i in range(len(expr) - 1):
                if expr[i] == '(': depth += 1
                elif expr[i] == ')': depth -= 1
                if depth == 0:
                    balanced = False
                    break
            if balanced:
                expr = expr[1:-1].strip()
            else:
                break


        # Helper to find top-level operators
        def find_top_level_op(pattern: str, text: str) -> re.Match | None:
            depth = 0
            in_dquote = False
            in_squote = False
            for m in re.finditer(pattern, text):
                # Check depth at the start of the match
                snippet = text[:m.start()]
                depth = snippet.count('(') - snippet.count(')')
                # Very simple quote check
                in_dquote = snippet.count('"') % 2 != 0
                in_squote = snippet.count("'") % 2 != 0
                if depth == 0 and not in_dquote and not in_squote:
                    return m
            return None

        comp_match = find_top_level_op(r'(>=|<=|==|>|<)', expr)
        if not comp_match:
            comp_match = find_top_level_op(r'\b(is greater than or equal to|is less than or equal to|is greater than|is less than|is equal to)\b', expr)

        if comp_match:
            left = expr[:comp_match.start()].strip()
            right = expr[comp_match.end():].strip()
            left_type = self._infer_expr_type(left, context=context)
            right_type = self._infer_expr_type(right, context=context)
            if not self._are_compatible(left_type, right_type):
                raise SemanticError(
                    f"Type mismatch in comparison ({context}): {left_type} and {right_type}"
                )
            return 'int'

        # Look for plus/minus last (lowest precedence)
        arith_match = find_top_level_op(r'\s([+\-])\s', expr)
        if not arith_match:
            # Look for Veritas-style plus/minus
            arith_match = find_top_level_op(r'\s(plus|minus)\s', expr)
            
        if not arith_match:
            # Then look for mult/div
            arith_match = find_top_level_op(r'\s([*/])\s', expr)
            
        if not arith_match:
            # Look for Veritas-style multiplied/divided
            arith_match = find_top_level_op(r'\s(multiplied by|divided by)\s', expr)

        if arith_match:
            left = expr[:arith_match.start()].strip()
            right = expr[arith_match.end():].strip()
            left_type = self._infer_expr_type(left, context=context)
            right_type = self._infer_expr_type(right, context=context)
            return self._binary_result_type(left_type, right_type, context)

        if expr.startswith('&'):
            base_type = self._infer_expr_type(expr[1:].strip(), context=context)
            return f'{base_type}*'

        if expr.startswith('*'):
            inner = expr[1:].strip()
            inner_type = self._infer_expr_type(inner, context=context)
            if not inner_type.endswith('*'):
                raise SemanticError(f"Cannot dereference non-pointer expression '{expr}'")
            return inner_type[:-1].strip() or 'void'
        if re.fullmatch(r'-?\d+', expr):
            return 'int'

        if re.fullmatch(r'-?\d+\.\d*', expr):
            return 'float'

        if '[' in expr and expr.endswith(']'):
            base = expr.split('[', 1)[0].strip()
            ctype = self._lookup(base)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{base}'")
            if ctype.endswith('*'):
                return ctype[:-1].strip() or 'void'
            return ctype

        if expr.startswith("'") and expr.endswith("'"):
            name = expr[1:-1]
            ctype = self._lookup(name)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{expr}'")
            return ctype

        ctype = self._lookup(expr)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{expr}'")
        return ctype

    def _binary_result_type(self, left: str, right: str, context: str) -> str:
        if left == 'string' and right == 'string':
            return 'string'
        numeric = {'int', 'float', 'double', 'double complex'}
        if left in numeric and right in numeric:
            if 'double complex' in (left, right):
                return 'double complex'
            if 'double' in (left, right):
                return 'double'
            if 'float' in (left, right):
                return 'float'
            return 'int'
        raise SemanticError(f"Type mismatch in binary expression ({context}): {left} and {right}")

    def _assert_assignable(self, target: str, value: str, context: str) -> None:
        if self._are_compatible(target, value):
            return
        raise SemanticError(f"Type mismatch in {context}: cannot assign {value} to {target}")

    def _are_compatible(self, left: str, right: str) -> bool:
        if left == right:
            return True
        if (left == 'string' and right == 'char*') or (left == 'char*' and right == 'string'):
            return True
        if left == 'string' and right == 'string':
            return True
        numeric = {'int', 'float', 'double', 'double complex'}
        return left in numeric and right in numeric
