from __future__ import annotations

from typing import Any


def format_ast_tree(node: Any, indent: int = 0, label: str | None = None) -> str:
    lines: list[str] = []
    pad = '  ' * indent

    if isinstance(node, dict):
        kind = node.get('kind', 'Node')
        header = kind[0].upper() + kind[1:]
        if label:
            lines.append(f'{pad}{label}: {header}')
        else:
            lines.append(f'{pad}{header}')
        for key, value in node.items():
            if key == 'kind':
                continue
            lines.append(format_ast_tree(value, indent + 1, key))
    elif isinstance(node, list):
        if label:
            lines.append(f'{pad}{label}')
            for item in node:
                lines.append(format_ast_tree(item, indent + 1))
        else:
            for item in node:
                lines.append(format_ast_tree(item, indent))
    else:
        if label:
            lines.append(f'{pad}{label}: {node}')
        else:
            lines.append(f'{pad}{node}')

    return '\n'.join(lines)
