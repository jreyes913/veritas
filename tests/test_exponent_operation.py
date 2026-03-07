import argparse
import textwrap
import unittest

from compiler.main import run
from vcparser import compile_veritas


class ExponentOperationTests(unittest.TestCase):
    def test_codegen_uses_pow_for_raised_to_the(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'exponent'.
            Create 'x' as an double with value 2.0.
            Create 'y' as an double with value 8.0.
            Create 'result' as an double with value 'x' raised to the 'y'.
            End of the program 'exponent'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('*result = pow(*x, *y);', c_src)

    def test_semantic_analysis_accepts_pow_expression(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'exponent'.
            Create 'x' as an double with value 2.0.
            Create 'y' as an double with value 8.0.
            Create 'result' as an double with value 'x' raised to the 'y'.
            End of the program 'exponent'.
            """
        )
        args = argparse.Namespace(tokens=False, ast=False, semantics=True, ir=False, format=False)
        symbols = run(src, args)
        self.assertIn('result', symbols)


if __name__ == '__main__':
    unittest.main()
