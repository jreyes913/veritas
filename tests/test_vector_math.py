import textwrap
import unittest
from vcparser import compile_veritas

class VectorMathTests(unittest.TestCase):
    def test_vector_addition_codegen(self):
        src = textwrap.dedent(
            """
            This is the program 'vmath'.
            Create 'v1' as a double vector of size 3.
            Create 'v2' as a double vector of size 3.
            Create 'v3' as a double vector of size 3.
            Replace 'v3' with the quantity 'v1' plus 'v2'.
            End of the program 'vmath'.
            """
        )
        c_src = compile_veritas(src)
        # Check that it generated a loop instead of simple pointer addition
        self.assertIn('for (int __i_0 = 0; __i_0 < 3; __i_0++)', c_src)
        self.assertIn('v3[__i_0] = v1[__i_0] + v2[__i_0]', c_src)
        self.assertNotIn('v3 = (v1 + v2)', c_src)

if __name__ == '__main__':
    unittest.main()
