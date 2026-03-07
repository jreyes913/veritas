from __future__ import annotations
from compiler.legacy import compile_veritas

# Legacy entry point for compatibility with old tests
def run(source: str, args=None) -> str:
    return compile_veritas(source)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            print(compile_veritas(f.read()))
