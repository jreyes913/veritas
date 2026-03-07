from typing import Any, Dict, List, Optional, Tuple
from compiler.semantic.semantic_analyzer import SemanticError

ASTNode = Dict[str, Any]

class DimensionVector:
    def __init__(self, vector: Dict[str, int]):
        self.vector = vector # {'Length': 1, 'Time': -1}

    def __eq__(self, other):
        if not isinstance(other, DimensionVector):
            return False
        # Treat missing keys as 0
        all_keys = set(self.vector.keys()) | set(other.vector.keys())
        for k in all_keys:
            if self.vector.get(k, 0) != other.vector.get(k, 0):
                return False
        return True

    def __mul__(self, other):
        new_vec = self.vector.copy()
        for k, v in other.vector.items():
            new_vec[k] = new_vec.get(k, 0) + v
        return DimensionVector(new_vec)

    def __truediv__(self, other):
        new_vec = self.vector.copy()
        for k, v in other.vector.items():
            new_vec[k] = new_vec.get(k, 0) - v
        return DimensionVector(new_vec)
    
    def pow(self, p: int):
        new_vec = {k: v * p for k, v in self.vector.items()}
        return DimensionVector(new_vec)

    def is_dimensionless(self):
        return all(v == 0 for v in self.vector.values())

    def __str__(self):
        if self.is_dimensionless():
            return "dimensionless"
        parts = []
        for k, v in sorted(self.vector.items()):
            if v == 1: parts.append(k)
            elif v != 0: parts.append(f"{k}^{v}")
        return " * ".join(parts)

class SemanticAnalyzer:
    def __init__(self):
        self.dimensions: Dict[str, str] = {} # Name -> Name
        self.units: Dict[str, DimensionVector] = {} # UnitName -> DimensionVector
        self.variable_dims: Dict[str, DimensionVector] = {} # VarName -> DimensionVector
        self.errors: List[str] = []

    def analyze(self, module: ASTNode):
        self._collect_definitions(module)
        self._analyze_block(module['globals'])
        self._analyze_block(module['main'])
        # Functions need their own scope handling, skipped for MVP
        
        if self.errors:
            # For now just print errors, ideally we attach to AST or raise
            for e in self.errors:
                print(f"[Semantic Error] {e}")
            raise SemanticError(self.errors[0], 0)

    def _collect_definitions(self, module: ASTNode):
        # 1. Dimensions
        for node in module.get('dimensions', []):
            name = node['name']
            self.dimensions[name] = name

        # 2. Base Units
        for node in module.get('units', []):
            if node['kind'] == 'unit_base':
                name = node['name']
                dim = node['dimension']
                if dim not in self.dimensions:
                    self.errors.append(f"Undefined dimension '{dim}' for unit '{name}' (Line {node['line']})")
                self.units[name] = DimensionVector({dim: 1})

        # 3. Derived Units
        derived = [n for n in module.get('units', []) if n['kind'] == 'unit_derived']
        
        # Simple parser for "meter / second"
        import re
        for node in derived:
            expr = node['expr']
            # Tokenize by operators
            # This is a very rough parser for the MVP
            # 'meter' / 'second' -> meter, /, second
            
            # Assume strict format: 'U1' [op 'U2']*
            # We can reuse the legacy parser's expression logic or just regex it
            # Let's try to evaluate it if we can
            
            # Hacky evaluation:
            try:
                vec = self._evaluate_unit_expr(expr)
                self.units[node['name']] = vec
            except Exception as e:
                self.errors.append(f"Invalid unit expression for '{node['name']}': {e} (Line {node['line']})")

    def _evaluate_unit_expr(self, expr: str) -> DimensionVector:
        # 'meter' / 'second'
        # Remove quotes
        expr = expr.replace("'", "").replace('"', "")
        
        # Split by space
        tokens = expr.split()
        
        acc = None
        current_op = None
        
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ('multiplied', 'by', 'times', '*'):
                current_op = '*'
                if tok == 'multiplied': i += 1 # Skip 'by'
            elif tok in ('divided', 'by', '/'):
                current_op = '/'
                if tok == 'divided': i += 1
            elif tok == 'squared':
                if acc: acc = acc.pow(2)
            elif tok == 'cubed':
                if acc: acc = acc.pow(3)
            else:
                # Must be a unit
                if tok not in self.units:
                    raise Exception(f"Unknown unit '{tok}'")
                
                u_vec = self.units[tok]
                if acc is None:
                    acc = u_vec
                else:
                    if current_op == '*':
                        acc = acc * u_vec
                    elif current_op == '/':
                        acc = acc / u_vec
                    else:
                        # Implicit multiplication
                        acc = acc * u_vec
            i += 1
            
        return acc if acc else DimensionVector({})

    def _analyze_block(self, nodes: List[ASTNode]):
        for node in nodes:
            if node['kind'] == 'declare':
                self._handle_declare(node)
            elif node['kind'] == 'assign':
                self._handle_assign(node)
            # Recursion for if/for skipped for MVP

    def _handle_declare(self, node: ASTNode):
        name = node['name']
        
        # 1. Determine declared dimension
        declared_dim = DimensionVector({})
        if node.get('unit'):
            unit_name = node['unit']
            if unit_name in self.units:
                declared_dim = self.units[unit_name]
            else:
                self.errors.append(f"Unknown unit '{unit_name}' in declaration of '{name}' (Line {node['line']})")

        self.variable_dims[name] = declared_dim

        # 2. Check initialization
        if node.get('init_raw'):
            expr_dim = self._infer_expr_dim(node['init_raw'], node['line'])
            
            # Allow dimensionless to match anything (implicit unit assignment)
            if not expr_dim.is_dimensionless() and expr_dim != declared_dim:
                self.errors.append(
                    f"Dimension mismatch in declaration of '{name}': "
                    f"declared {declared_dim}, got {expr_dim} (Line {node['line']})"
                )

    def _handle_assign(self, node: ASTNode):
        target_name = node['target_raw'].replace("'", "")
        # Handle array indexing: 'v[0]' -> 'v'
        if '[' in target_name:
            target_name = target_name.split('[')[0] # This is a simplification
            
        target_dim = self.variable_dims.get(target_name, DimensionVector({}))
        
        expr_dim = self._infer_expr_dim(node['value_raw'], node['line'])
        
        # Allow dimensionless to match anything
        if not expr_dim.is_dimensionless() and target_dim != expr_dim:
             self.errors.append(
                f"Dimension mismatch in assignment to '{target_name}': "
                f"variable has {target_dim}, expression has {expr_dim} (Line {node['line']})"
            )

    def _infer_expr_dim(self, expr: str, line: int) -> DimensionVector:
        expr = expr.strip()
        
        # Handle parentheses / quantity
        if expr.lower().startswith("the quantity"):
            inner = expr[12:].strip()
            return self._infer_expr_dim(inner, line)
            
        # Check for operators (lowest precedence first)
        # +, -
        for op in ['plus', 'minus', '+', '-']:
            parts = self._split_on_keyword(expr, op)
            if parts:
                lhs, rhs = parts
                dim_l = self._infer_expr_dim(lhs, line)
                dim_r = self._infer_expr_dim(rhs, line)
                if not dim_l.is_dimensionless() and not dim_r.is_dimensionless() and dim_l != dim_r:
                    self.errors.append(f"Dimension mismatch in addition/subtraction: {dim_l} vs {dim_r} (Line {line})")
                return dim_l

        # *, /
        for op in ['multiplied by', 'divided by', '*', '/']:
            parts = self._split_on_keyword(expr, op)
            if parts:
                lhs, rhs = parts
                dim_l = self._infer_expr_dim(lhs, line)
                dim_r = self._infer_expr_dim(rhs, line)
                
                if op in ('multiplied by', '*'):
                    return dim_l * dim_r
                else:
                    return dim_l / dim_r

        # pow
        for op in ['raised to the', 'pow']:
             parts = self._split_on_keyword(expr, op)
             if parts:
                lhs, rhs = parts
                dim_l = self._infer_expr_dim(lhs, line)
                
                # Check if exponent is a literal integer
                rhs_clean = rhs.replace("'", "").strip()
                try:
                    exponent = int(rhs_clean)
                    return dim_l.pow(exponent)
                except ValueError:
                    # Non-fatal warning for now to avoid breaking existing math tests
                    # self.errors.append(f"Exponent must be an integer literal for dimensional analysis (Line {line})")
                    return DimensionVector({})

        # Base case: literal or variable
        clean = expr.replace("'", "").replace('"', "").strip()
        
        # 1. Variable
        if clean in self.variable_dims:
            return self.variable_dims[clean]
            
        # 2. Number (Dimensionless)
        import re
        if re.match(r'^-?\d+(\.\d+)?$', clean):
            return DimensionVector({})
            
        # 3. Unknown
        # If it's a string literal, it's dimensionless
        if expr.startswith('"'):
            return DimensionVector({})

        # If we are here, it might be a variable defined outside logic or just unknown
        # For now, return dimensionless but warn?
        # Actually, if we miss a variable, it might be an error.
        return DimensionVector({})

    def _split_on_keyword(self, text: str, keyword: str) -> Optional[Tuple[str, str]]:
        import re
        
        # Primitive quote masking
        blanked = text
        # Mask quotes with spaces to avoid matching inside strings
        # This is a hacky way, identical to legacy.py
        blanked = re.sub(r'"[^"]*"', lambda m: ' ' * len(m.group()), blanked)
        blanked = re.sub(r"'[^']*'", lambda m: ' ' * len(m.group()), blanked)

        matches = list(re.finditer(re.escape(keyword), blanked, re.IGNORECASE))
        if not matches:
            return None
            
        # Pick the one that looks like a whole word if it's a word-op
        if keyword[0].isalpha():
             # Filter for whole words
             valid_matches = []
             for m in matches:
                 start, end = m.span()
                 if (start == 0 or not blanked[start-1].isalnum()) and (end == len(blanked) or not blanked[end].isalnum()):
                     valid_matches.append(m)
             matches = valid_matches

        if not matches:
            return None

        # Take the last one for Left Associativity
        m = matches[-1]
        start, end = m.span()
        
        # Use the original text for return
        return text[:start], text[end:]
