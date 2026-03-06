from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Symbol:
    name: str
    ctype: str
    scope: str


class SymbolTable:
    def __init__(self) -> None:
        self._symbols: list[Symbol] = []

    def define(self, name: str, ctype: str, scope: str) -> None:
        self._symbols.append(Symbol(name=name, ctype=ctype, scope=scope))

    def as_rows(self) -> list[tuple[str, str, str]]:
        return sorted((s.name, s.ctype, s.scope) for s in self._symbols)


def format_symbol_table(table: SymbolTable) -> str:
    rows = table.as_rows()
    if not rows:
        return 'Symbol table is empty.'
    width_name = max(len('NAME'), *(len(name) for name, _, _ in rows))
    width_type = max(len('TYPE'), *(len(ctype) for _, ctype, _ in rows))
    width_scope = max(len('SCOPE'), *(len(scope) for _, _, scope in rows))
    header = f"{'NAME':<{width_name}}  {'TYPE':<{width_type}}  {'SCOPE':<{width_scope}}"
    sep = '-' * len(header)
    body = [f"{name:<{width_name}}  {ctype:<{width_type}}  {scope:<{width_scope}}" for name, ctype, scope in rows]
    return '\n'.join([header, sep, *body])
