import argparse
import textwrap
import unittest

from compiler.main import run
from compiler.semantic.semantic_analyzer import SemanticError


class VectorMatrixArrayTypeTests(unittest.TestCase):
    def test_numeric_array_is_rejected(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'bad_array'.
            Create 'a' as a double array of size 3 with values:
                1.0,
                2.0,
                and 3.0.
            End of the program 'bad_array'.
            """
        )
        args = argparse.Namespace(tokens=False, ast=False, semantics=True, ir=False, format=False)
        with self.assertRaises(SemanticError):
            run(src, args)

    def test_vector_supports_numeric_math(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'vector_math'.
            Create 'v' as a double vector of size 3 with values:
                1.0,
                2.0,
                and 3.0.
            Create 'w' as a double vector of size 3 with values:
                3.0,
                2.0,
                and 1.0.
            Create 'result' as a double vector of size 3.
            Replace 'result' with the quantity 'v' plus 'w'.
            End of the program 'vector_math'.
            """
        )
        args = argparse.Namespace(tokens=False, ast=False, semantics=True, ir=False, format=False)
        symbols = run(src, args)
        self.assertIn('v', symbols)
        self.assertIn('result', symbols)

    def test_matrix_declaration_is_available(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'matrix_decl'.
            Create 'data' as a matrix with columns: "temperature", and "label".
            End of the program 'matrix_decl'.
            """
        )
        args = argparse.Namespace(tokens=False, ast=False, semantics=True, ir=False, format=False)
        symbols = run(src, args)
        self.assertIn('data', symbols)


if __name__ == '__main__':
    unittest.main()
