from __future__ import annotations

from compiler.legacy import CodeGen
from compiler.ir.ir_nodes import IRProgram


def generate_c(ir_program: IRProgram) -> str:
    module = {
        'includes': ir_program.includes,
        'globals': ir_program.globals,
        'functions': ir_program.functions,
        'main': ir_program.main,
    }
    return CodeGen().generate(module)
