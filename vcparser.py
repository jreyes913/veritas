from __future__ import annotations

import argparse
import sys

from compiler.main import run


def compile_veritas(source: str) -> str:
    args = argparse.Namespace(tokens=False, ast=False, ir=False, format=False, source='')
    return run(source, args)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 vcparser.py <source.ver>', file=sys.stderr)
        raise SystemExit(1)
    with open(sys.argv[1]) as fh:
        print(compile_veritas(fh.read()), end='')
