from compiler.cli import main
from compiler.legacy import compile_veritas

def run(source: str, args=None) -> str:
    # Minimal compatibility wrapper for legacy tests
    return compile_veritas(source)

if __name__ == "__main__":
    main()
