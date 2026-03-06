from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IRInstruction:
    op: str
    args: tuple[Any, ...] = ()


@dataclass
class IRProgram:
    includes: list[Any]
    globals: list[Any]
    functions: list[Any]
    main: list[Any]
    instructions: list[IRInstruction]
