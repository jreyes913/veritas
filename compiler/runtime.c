#include <stdlib.h>
#include <string.h>

typedef struct {
    unsigned char *memory;
    size_t capacity;
    size_t offset;
} Arena;

extern Arena *global_arena;
void* arena_alloc(Arena *arena, size_t size);

char* join(const char* s1, const char* s2) {
    size_t l1 = strlen(s1);
    size_t l2 = strlen(s2);
    char* res = arena_alloc(global_arena, l1 + l2 + 1);
    memcpy(res, s1, l1);
    memcpy(res + l1, s2, l2);
    res[l1 + l2] = '\0';
    return res;
}
