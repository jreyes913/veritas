from __future__ import annotations

import argparse
from pathlib import Path

from compiler.main import run


def compile_veritas(source: str) -> str:
    args = argparse.Namespace(tokens=False, ast=False, ir=False, semantics=False, format=False, source='')
    return run(source, args)


def main() -> None:
    ap = argparse.ArgumentParser(description='Veritas compiler compatibility entrypoint')
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
