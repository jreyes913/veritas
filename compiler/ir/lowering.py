from __future__ import annotations

from compiler.ir.ir_nodes import IRInstruction, IRProgram


def _walk_stmt(node: dict, out: list[IRInstruction]) -> None:
    kind = node.get('kind')
    if kind == 'declare':
        out.append(IRInstruction('DECLARE', (node['ctype'], node['name'])))
    elif kind == 'assign':
        out.append(IRInstruction('ASSIGN', (node['target'], node['value'])))
    elif kind == 'call':
        out.append(IRInstruction('CALL', (node['func'], tuple(node['args']), node['dest'])))
    elif kind == 'for':
        out.append(IRInstruction('FOR_BEGIN', (node['var'], node['start'], node['inclusive'], node['end'])))
        for child in node['body']:
            _walk_stmt(child, out)
        out.append(IRInstruction('FOR_END', ()))
    elif kind == 'if':
        out.append(IRInstruction('IF_BEGIN', (node['condition'],)))
        for child in node['then_body']:
            _walk_stmt(child, out)
        if node['else_body']:
            out.append(IRInstruction('ELSE', ()))
            for child in node['else_body']:
                _walk_stmt(child, out)
        out.append(IRInstruction('IF_END', ()))
    elif kind == 'error':
        out.append(IRInstruction('ERROR', (node['message'], node['raw'])))


def lower_program(ast_program: dict) -> IRProgram:
    instructions: list[IRInstruction] = []
    for stmt in ast_program['main']:
        _walk_stmt(stmt, instructions)
    return IRProgram(
        includes=ast_program['includes'],
        globals=ast_program['globals'],
        functions=ast_program['functions'],
        main=ast_program['main'],
        instructions=instructions,
    )


def format_ir(ir_program: IRProgram) -> str:
    lines: list[str] = []
    for ins in ir_program.instructions:
        lines.append(ins.op if not ins.args else f"{ins.op} {' '.join(map(str, ins.args))}")
    return '\n'.join(lines)
