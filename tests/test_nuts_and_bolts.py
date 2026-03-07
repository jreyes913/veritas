import textwrap
import unittest
from vcparser import compile_veritas

class NutsAndBoltsTests(unittest.TestCase):
    def test_indexed_replacement(self):
        src = textwrap.dedent(
            """
            This is the program 'index_test'.
            Create 'v' as a double vector of size 10.
            Replace 'v' at index 5 with 123.45.
            End of the program 'index_test'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('v[5] = 123.45;', c_src)

    def test_complex_loop_with_indexing(self):
        src = textwrap.dedent(
            """
            This is the program 'loop_test'.
            Create 'data' as a double vector of size 5 with values: 1.0, 2.0, 3.0, 4.0, and 5.0.
            Create 'i' as an int.
            For every iteration of 'i' from 0 to 5:
                Create 'x' as a double with value an element of 'data' at index 'i'.
                Replace 'data' at index 'i' with the quantity 'x' multiplied by 2.0.
            End iteration of 'i' from 0 to 5.
            End of the program 'loop_test'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('for (; *i < 5; (*i)++)', c_src)
        self.assertIn('*x = data[*i];', c_src)
        self.assertIn('data[*i] = (*x * 2.0);', c_src)

    def test_exponent_operation(self):
        src = textwrap.dedent(
            """
            This is the program 'exp_test'.
            Create 'base' as a double with value 2.0.
            Create 'exp' as a double with value 3.0.
            Create 'res' as a double with value 'base' raised to the 'exp'.
            End of the program 'exp_test'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('*res = pow(*base, *exp);', c_src)

if __name__ == '__main__':
    unittest.main()
