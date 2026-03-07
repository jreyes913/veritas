from __future__ import annotations

import argparse
from pathlib import Path

from compiler.ast.nodes import format_ast_tree
from compiler.backends.c_backend import generate_c
from compiler.frontend.lexer import format_tokens, tokenize
from compiler.frontend.parser import Parser
from compiler.ir.lowering import format_ir, lower_program
from compiler.semantic import SemanticAnalyzer, format_symbol_table


def _fmt_decl(d: dict) -> str:
    container = d.get('container', 'array' if d.get('is_array') else 'scalar')
    if container in {'array', 'vector'}:
        base = f"Create '{d['name']}' as a {d['ctype']} {container} of size {d['size']}"
        if d['init']:
            return base + ' with values ' + ', '.join(d['init']) + '.'
        return base + '.'
    if container == 'matrix':
        cols = d.get('columns') or []
        if cols:
            return f"Create '{d['name']}' as a matrix with columns: " + ', '.join(cols) + '.'
        return f"Create '{d['name']}' as a matrix."
    if d['init'] is not None:
        return f"Create '{d['name']}' as {d['ctype']} with value {d['init']}."
    return f"Create '{d['name']}' as {d['ctype']}."


def _fmt_nodes(nodes: list[dict], indent: int) -> list[str]:
    pad = '    ' * indent
    out: list[str] = []
    for n in nodes:
        k = n['kind']
        if k == 'declare':
            out.append(pad + _fmt_decl(n))
        elif k == 'assign':
            out.append(pad + f"Replace {n['target']} with {n['value']}.")
        elif k == 'call':
            args = f" with {', '.join(n['args'])}" if n['args'] else ''
            dest = n['dest'] if n['dest'] is not None else 'nothing'
            out.append(pad + f"Call '{n['func']}'{args} and save the result to {dest}.")
        elif k == 'load':
            typ = n['type']
            if typ == 'bin matrix':
                out.append(pad + f"Load '{n['name']}' from \"{n['path']}\" as bin matrix with size {n['rows']} by {n['cols']}.")
            else:
                out.append(pad + f"Load '{n['name']}' from \"{n['path']}\" as matrix.")
        elif k == 'for':
            bound = 'through' if n['inclusive'] else 'to'
            out.append(pad + f"For every iteration of '{n['var']}' from {n['start']} {bound} {n['end']}")
            out.extend(_fmt_nodes(n['body'], indent + 1))
            out.append(pad + f"End iteration of '{n['var']}' from {n['start']} {bound} {n['end']}.")
        elif k == 'if':
            out.append(pad + f"If {n['condition']}:")
            out.extend(_fmt_nodes(n['then_body'], indent + 1))
            if n['else_body']:
                out.append(pad + 'Otherwise:')
                out.extend(_fmt_nodes(n['else_body'], indent + 1))
            out.append(pad + 'End if block.')
    return out


def format_veritas(ast_program: dict) -> str:
    name = ast_program.get('name') or 'program'
    lines = [f"This is the program '{name}'."]
    for i in ast_program['includes']:
        lines.append(f"Include the header '{i['path']}'.")
    for g in ast_program['globals']:
        lines.append(_fmt_decl(g))
    for f in ast_program['functions']:
        params = ', '.join(f"'{n}' as a {t}" for t, n in f['params'])
        sig = f"Define the function '{f['name']}'"
        if params:
            sig += f' with {params}'
        if f['ret_type'] != 'void':
            sig += f" returning {f['ret_type']}"
        lines.append(sig + '.')
        lines.extend(_fmt_nodes(f['body'], 1))
        lines.append(f"End function '{f['name']}'.")
    lines.extend(_fmt_nodes(ast_program['main'], 0))
    lines.append(f"End of the program '{name}'.")
    return '\n'.join(lines)


def run(source: str, args: argparse.Namespace) -> str:
    tokens = tokenize(source)
    if args.tokens:
        return format_tokens(tokens)

    parser = Parser()
    for tok in tokens:
        if tok.kind == 'STATEMENT':
            parser.feed(tok.value)
    ast_program = parser.ast()

    if args.ast:
        return format_ast_tree(ast_program)
    if args.format:
        return format_veritas(ast_program)

    analyzer = SemanticAnalyzer()
    symbol_table = analyzer.analyze(ast_program)
    if args.semantics:
        return format_symbol_table(symbol_table)

    ir_program = lower_program(ast_program)
    if args.ir:
        return format_ir(ir_program)

    return generate_c(ir_program, symbols=symbol_table)


def main() -> None:
    ap = argparse.ArgumentParser(description='Veritas compiler')
    ap.add_argument('source')
    ap.add_argument('--tokens', action='store_true')
    ap.add_argument('--ast', action='store_true')
    ap.add_argument('--ir', action='store_true')
    ap.add_argument('--semantics', action='store_true')
    ap.add_argument('--format', action='store_true')
    args = ap.parse_args()
    source = Path(args.source).read_text()
    print(run(source, args), end='')


if __name__ == '__main__':
    main()
