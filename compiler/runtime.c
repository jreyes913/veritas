#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <complex.h>

typedef struct {
    unsigned char *memory;
    size_t capacity;
    size_t offset;
} Arena;

extern Arena *global_arena;
void* arena_alloc(Arena *arena, size_t size);

typedef struct {
    double* data;
    int size;
} Vector;

typedef struct {
    double* data;
    int rows;
    int cols;
    char** column_names;
} Matrix;

char* join(const char* s1, const char* s2) {
    size_t l1 = strlen(s1);
    size_t l2 = strlen(s2);
    char* res = arena_alloc(global_arena, l1 + l2 + 1);
    memcpy(res, s1, l1);
    memcpy(res + l1, s2, l2);
    res[l1 + l2] = '\0';
    return res;
}

/* Vector and Matrix operations - Use double complex for maximum flexibility */
void vector_add(double complex* a, double complex* b, double complex* out, int size) {
    for (int i = 0; i < size; i++) {
        out[i] = a[i] + b[i];
    }
}

void vector_sub(double complex* a, double complex* b, double complex* out, int size) {
    for (int i = 0; i < size; i++) {
        out[i] = a[i] - b[i];
    }
}

void vector_mul(double complex* a, double complex* b, double complex* out, int size) {
    for (int i = 0; i < size; i++) {
        out[i] = a[i] * b[i];
    }
}

void vector_mul_scalar(double complex* a, double complex scalar, double complex* out, int size) {
    for (int i = 0; i < size; i++) {
        out[i] = a[i] * scalar;
    }
}

/* GSL stubs or basic implementations */
double mean(double* data, int n) {
    double sum = 0;
    for (int i = 0; i < n; i++) sum += data[i];
    return sum / n;
}

double standard_deviation(double* data, int n) {
    double m = mean(data, n);
    double sum_sq = 0;
    for (int i = 0; i < n; i++) sum_sq += (data[i] - m) * (data[i] - m);
    return sqrt(sum_sq / n);
}
