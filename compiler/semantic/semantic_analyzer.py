from __future__ import annotations

import re
import sys
from typing import Optional

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
        'sample_mean': 'double',
        'population_mean': 'double',
        'sample_variance': 'double',
        'population_variance': 'double',
        'sample_std': 'double',
        'population_std': 'double',
        'median': 'double',
        'mode': 'double',
        'quantile': 'double',
        'iqr': 'double',
        'covariance': 'double',
        'correlation': 'double',
        'skewness': 'double',
        'kurtosis': 'double',
        # Inferential Statistics & Probability
        't_test': 'double',
        'paired_t_test': 'double',
        'chi_square_test': 'double',
        'anova_one_way': 'double',
        'mean_confidence_interval': 'void',
        'proportion_confidence_interval': 'void',
        'normal_pdf': 'double',
        'normal_cdf': 'double',
        'normal_inverse_cdf': 'double',
        'student_t_cdf': 'double',
        'student_t_inverse_cdf': 'double',
        'chi_square_cdf': 'double',
        'chi_square_inverse_cdf': 'double',
        'f_cdf': 'double',
        'f_inverse_cdf': 'double',
        'sample_normal': 'double',
        'sample_uniform': 'double',
        'sample_poisson': 'double',
        'matrix_get_column': 'double*',
        'matrix_get_column_idx': 'double*',
        # Linear Algebra
        'solve_linear_system': 'void',
        'matrix_multiply': 'void',
        'invert_matrix': 'void',
        'determinant': 'double',
        'trace': 'double',
        'transpose': 'void',
        'eigenvalues': 'void',
        'eigenvectors': 'void',
        'lu_decompose': 'void',
        'qr_decompose': 'void',
        'svd': 'void',
        'vector_norm': 'double',
        'matrix_norm': 'double',
        'condition_number': 'double',
        # Signal Processing
        'fft_forward': 'void',
        'fft_backward': 'void',
    }

    NUMERIC_PRIMITIVES = {'int', 'float', 'double', 'double complex'}

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

    def _define(self, name: str, ctype: str, scope: str, size: Optional[int] = None) -> None:
        self._scope_stack[-1][name] = ctype
        self.symbols.define(name, ctype, scope, size)

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
            elif kind == 'load':
                self._handle_load(node, scope)
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
        container = node.get('container', 'array' if node.get('is_array') else 'scalar')
        size = node.get('size')

        if container == 'indexed_scalar':
            source_container = node['source_container'].replace('\x00', ' ').strip()
            source_type = self._lookup(source_container)
            if source_type is None:
                raise SemanticError(f"Undefined container '{source_container}'")
            if source_type.startswith('vector<') and source_type.endswith('>'):
                ctype = source_type[7:-1].strip()
            elif source_type.startswith('array<') and source_type.endswith('>'):
                ctype = source_type[6:-1].strip()
            else:
                # Fallback or error if not a container
                ctype = source_type
            node['ctype'] = ctype # Update AST node with inferred type
            container = 'scalar' # Treat as scalar for the rest of this method

        if container == 'vector' and not self._is_numeric_type(ctype):
            raise SemanticError(
                f"Vector '{name}' must use a numeric primitive type, got {ctype}"
            )

        if container == 'array' and self._is_numeric_type(ctype):
            raise SemanticError(
                f"Array '{name}' is restricted to non-numeric types, got {ctype}. "
                "Use a vector for numeric sequences."
            )

        declared_type = ctype
        if container == 'vector':
            declared_type = f'vector<{ctype}>'
        elif container == 'array':
            declared_type = f'array<{ctype}>'
        elif container == 'matrix':
            declared_type = 'matrix'

        self._define(name, declared_type, scope, size=size)

        init = node.get('init')
        if container in {'array', 'vector'}:
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
            def _clean_and(s: str) -> str:
                if s.lower().startswith('and ') and s.count('"') % 2 == 0:
                    m = re.match(r'^and\s+(.+)', s, re.IGNORECASE)
                    return m.group(1).strip() if m else s
                return s
            arg = _clean_and(arg)
            self._infer_expr_type(arg, context=f"argument to '{func_name}'")
        
        dest = node.get('dest')
        if dest is not None:
            dest_type = self._infer_target_type(dest)
            
            # Check if it's a blessed function
            if func_name in self.BLESSED_FUNCTIONS:
                ret_type = self.BLESSED_FUNCTIONS[func_name]
                if ret_type != 'void':
                    self._assert_assignable(dest_type, ret_type, f"result of '{func_name}'")

    def _handle_load(self, node: dict, scope: str) -> None:
        name = node['name'].replace('\x00', ' ').strip()
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        self._define(name, 'matrix', scope)

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
            if ctype.startswith('vector<') and ctype.endswith('>'):
                return ctype[7:-1].strip()
            if ctype.startswith('array<') and ctype.endswith('>'):
                return ctype[6:-1].strip()
            if ctype.endswith('*'):
                return ctype[:-1].strip() or 'void'
            return ctype

        ctype = self._lookup(target)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{target}'")
        return ctype

    def _infer_expr_type(self, expr: str, context: str = 'expression') -> str:
        # Unprotect null bytes if present from legacy parser protection
        expr = expr.replace('\x00', ' ').strip()
        if not expr:
            return 'void'

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

        if not expr: return 'void'

        pow_args = self._split_pow_args(expr)
        if pow_args:
            left, right = pow_args
            self._infer_expr_type(left, context=f"{context} (base)")
            self._infer_expr_type(right, context=f"{context} (exponent)")
            return 'double'

        m_elem = re.match(r"an[\s\x00]element[\s\x00]of[\s\x00]'(\w+)'[\s\x00]at[\s\x00]index[\s\x00](?:'(.+?)'|(\w+))", expr)
        if m_elem:
            var_name = m_elem.group(1)
            idx = m_elem.group(2) or m_elem.group(3)
            ctype = self._lookup(var_name)
            if ctype is None:
                raise SemanticError(f"Undefined variable '{var_name}'")
            if ctype.startswith('vector<') and ctype.endswith('>'):
                return ctype[7:-1].strip()
            if ctype.startswith('array<') and ctype.endswith('>'):
                return ctype[6:-1].strip()
            return ctype

        if expr.lower().startswith('the quantity '):
            return self._infer_expr_type(expr[len('the quantity '):].strip(), context=context)

        if expr.startswith('strcmp(') and expr.endswith(')') or 'strcmp(' in expr:
            return 'int'

        pow_args = self._split_pow_args(expr)
        if pow_args is not None:
            left_type = self._infer_expr_type(pow_args[0], context=context)
            right_type = self._infer_expr_type(pow_args[1], context=context)
            return self._binary_result_type(left_type, right_type, context)
        
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

        if not arith_match:
            arith_match = find_top_level_op(r'\s(raised to the)\s', expr)

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
            if ctype.startswith('vector<') and ctype.endswith('>'):
                return ctype[7:-1].strip()
            if ctype.startswith('array<') and ctype.endswith('>'):
                return ctype[6:-1].strip()
            if ctype.endswith('*'):
                return ctype[:-1].strip() or 'void'
            return ctype

        if expr.startswith("'") and expr.endswith("'"):
            expr = expr[1:-1].strip()

        ctype = self._lookup(expr)
        if ctype is None:
            raise SemanticError(f"Undefined variable '{expr}'")
        return ctype

    def _split_pow_args(self, expr: str) -> tuple[str, str] | None:
        if not (expr.startswith('pow(') and expr.endswith(')')):
            return None

        inner = expr[4:-1].strip()
        depth = 0
        in_dquote = False
        in_squote = False
        for i, ch in enumerate(inner):
            if ch == '"' and not in_squote:
                in_dquote = not in_dquote
            elif ch == "'" and not in_dquote:
                in_squote = not in_squote
            elif not in_dquote and not in_squote:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    left = inner[:i].strip()
                    right = inner[i + 1:].strip()
                    if left and right:
                        return left, right
        return None

    def _binary_result_type(self, left: str, right: str, context: str) -> str:
        if left == 'string' and right == 'string':
            return 'string'

        left_container = self._container_of(left)
        right_container = self._container_of(right)

        if left_container == 'matrix' or right_container == 'matrix':
            raise SemanticError(
                f"Matrix arithmetic is not supported in scalar expressions ({context}); "
                "use dedicated matrix operations/functions."
            )

        if left_container == 'array' or right_container == 'array':
            raise SemanticError(
                f"Array values are non-numeric and cannot be used in math ({context})."
            )

        if left_container == 'vector' and right_container in {'vector', 'scalar'}:
            return left
        if right_container == 'vector' and left_container == 'scalar':
            return right

        if self._is_numeric_type(left) and self._is_numeric_type(right):
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

        if self._container_of(left) == 'matrix' or self._container_of(right) == 'matrix':
            return left == right

        if self._container_of(left) == 'array' or self._container_of(right) == 'array':
            return left == right

        if self._container_of(left) == 'vector' and self._container_of(right) == 'scalar':
            # Allow assigning T* to vector<T> (runtime return of pointers to data)
            if left.endswith(f'<{right.rstrip("*")}>'):
                return True
            if right.endswith('*') and left.startswith('vector<') and left.endswith('>'):
                 inner = left[7:-1].strip()
                 if right[:-1].strip() == inner:
                     return True
            return left == right

        return self._is_numeric_type(left) and self._is_numeric_type(right)

    def _is_numeric_type(self, ctype: str) -> bool:
        return ctype in self.NUMERIC_PRIMITIVES

    def _container_of(self, ctype: str) -> str:
        if ctype.startswith('vector<') and ctype.endswith('>'):
            return 'vector'
        if ctype == 'matrix':
            return 'matrix'
        if ctype.startswith('array<') and ctype.endswith('>'):
            return 'array'
        return 'scalar'
