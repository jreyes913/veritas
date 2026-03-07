import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from vcparser import compile_veritas


class ArenaAllocatorTests(unittest.TestCase):
    def test_scalar_allocation_codegen(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'scalar'.
            Create 'x' as an int with value 5.
            End of the program 'scalar'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('Arena arena = arena_create(16 * 1024 * 1024);', c_src)
        self.assertIn('int *x;', c_src)
        self.assertIn('x = arena_alloc(&arena, sizeof(int)); *x = 5;', c_src)

    def test_array_allocation_codegen(self) -> None:
        src = textwrap.dedent(
            """
            This is the program 'array'.
            Create 't' as a double vector of size 100.
            End of the program 'array'.
            """
        )
        c_src = compile_veritas(src)
        self.assertIn('double *t = arena_alloc(&arena, 100 * sizeof(double));', c_src)

    def test_arena_overflow_handling(self) -> None:
        c_src = textwrap.dedent(
            """
            #include <stdlib.h>
            #include <stdio.h>
            #include <stddef.h>

            typedef struct {
                unsigned char *memory;
                size_t capacity;
                size_t offset;
            } Arena;

            Arena arena_create(size_t size) {
                Arena arena;
                arena.memory = malloc(size);
                arena.capacity = size;
                arena.offset = 0;
                return arena;
            }

            void* arena_alloc(Arena *arena, size_t size) {
                if (arena->offset + size > arena->capacity) {
                    fprintf(stderr, "Arena out of memory\\n");
                    exit(1);
                }
                void *ptr = arena->memory + arena->offset;
                arena->offset += size;
                return ptr;
            }

            void arena_destroy(Arena *arena) {
                free(arena->memory);
            }

            int main(void) {
                Arena arena = arena_create(8);
                (void)arena_alloc(&arena, 4);
                (void)arena_alloc(&arena, 5);
                arena_destroy(&arena);
                return 0;
            }
            """
        )
        with tempfile.TemporaryDirectory() as td:
            c_file = Path(td) / 'overflow.c'
            bin_file = Path(td) / 'overflow'
            c_file.write_text(c_src)
            subprocess.run(['gcc', str(c_file), '-o', str(bin_file)], check=True)
            proc = subprocess.run([str(bin_file)], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('Arena out of memory', proc.stderr)


if __name__ == '__main__':
    unittest.main()
