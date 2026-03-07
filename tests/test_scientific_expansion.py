import argparse
import textwrap
import unittest

from compiler.main import run
from vcparser import compile_veritas


class ScientificExpansionTests(unittest.TestCase):
    def test_codegen_adds_stats_and_linalg_prototypes(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'scientific_prototypes'.
            Create 'x' as a double vector of size 3 with values:
                1.0,
                2.0,
                and 3.0.
            Create 'n' as an int with value 3.
            Create 'm' as a double.
            Create 's' as a double.
            Create 'det' as a double.
            Call 'sample_mean' with 'x' and 'n' stored to 'm'.
            Call 'sample_std' with 'x' and 'n' stored to 's'.
            Call 'determinant' with 'x' and 'n' stored to 'det'.
            End of the program 'scientific_prototypes'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('double sample_mean(double* data, int n);', c_src)
        self.assertIn('double sample_std(double* data, int n);', c_src)
        self.assertIn('double determinant(double* a, int n);', c_src)

    def test_codegen_triggers_gsl_headers_from_new_calls(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'scientific_headers'.
            Create 'x' as a double vector of size 3 with values:
                1.0,
                2.0,
                and 3.0.
            Create 'y' as a double vector of size 3 with values:
                2.0,
                3.0,
                and 4.0.
            Create 'n' as an int with value 3.
            Create 'out' as a double.
            Call 't_test' with 'x', 'n', 'y', and 'n' stored to 'out'.
            Call 'eigenvalues' with 'x', 'n', 'y', and 'y' stored to nothing.
            End of the program 'scientific_headers'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('#include <gsl/gsl_cdf.h>', c_src)
        self.assertIn('#include <gsl/gsl_statistics.h>', c_src)
        self.assertIn('#include <gsl/gsl_eigen.h>', c_src)

    def test_semantics_accepts_new_blessed_function_returns(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'scientific_semantics'.
            Create 'x' as a double vector of size 3 with values:
                1.0,
                2.0,
                and 3.0.
            Create 'n' as an int with value 3.
            Create 'm' as a double.
            Create 'cdf' as a double.
            Create 'det' as a double.
            Call 'sample_mean' with 'x' and 'n' stored to 'm'.
            Call 'normal_cdf' with 0.0, 0.0, and 1.0 stored to 'cdf'.
            Call 'determinant' with 'x' and 'n' stored to 'det'.
            End of the program 'scientific_semantics'.
            """
        )
        args = argparse.Namespace(tokens=False, ast=False, semantics=True, ir=False, format=False)
        symbols = run(src, args)
        self.assertIn('m', symbols)
        self.assertIn('cdf', symbols)
        self.assertIn('det', symbols)


if __name__ == '__main__':
    unittest.main()
