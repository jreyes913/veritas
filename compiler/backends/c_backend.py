from __future__ import annotations

from compiler.legacy import CodeGen
from compiler.ir.ir_nodes import IRProgram
from compiler.semantic.symbol_table import SymbolTable


def generate_c(ir_program: IRProgram, symbols: SymbolTable | None = None) -> str:
    module = {
        'includes': ir_program.includes,
        'globals': ir_program.globals,
        'functions': ir_program.functions,
        'main': ir_program.main,
    }
    return CodeGen(symbols=symbols).generate(module)
