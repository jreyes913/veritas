from __future__ import annotations

import re

from compiler.semantic.symbol_table import SymbolTable


class SemanticError(Exception):
    pass


class SemanticAnalyzer:
    def __init__(self) -> None:
        self.symbols = SymbolTable()
        self._scope_stack: list[dict[str, str]] = [dict()]

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
        for arg in node.get('args', []):
            self._infer_expr_type(arg, context=f"argument to '{node['func']}'")
        dest = node.get('dest')
        if dest is not None:
            self._infer_target_type(dest)

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

        base = target.split('[', 1)[0].strip()
        ctype = self._lookup(base)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{base}'")
        return ctype

    def _infer_expr_type(self, expr: str, context: str = 'expression') -> str:
        expr = expr.strip()
        if not expr:
            return 'void'

        if expr.startswith('(') and expr.endswith(')'):
            return self._infer_expr_type(expr[1:-1], context=context)

        comp_match = re.search(r'(>=|<=|==|>|<)', expr)
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

        m = re.search(r'\s([+\-*/])\s', expr)
        if m:
            left = expr[:m.start()].strip()
            right = expr[m.end():].strip()
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

        if expr.startswith('"') and expr.endswith('"'):
            return 'string'

        if '[' in expr and expr.endswith(']'):
            base = expr.split('[', 1)[0].strip()
            ctype = self._lookup(base)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{base}'")
            if ctype.endswith('*'):
                return ctype[:-1].strip() or 'void'
            return ctype

        ctype = self._lookup(expr)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{expr}'")
        return ctype

    def _binary_result_type(self, left: str, right: str, context: str) -> str:
        numeric = {'int', 'float', 'double'}
        if left in numeric and right in numeric:
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
        numeric = {'int', 'float', 'double'}
        return left in numeric and right in numeric
