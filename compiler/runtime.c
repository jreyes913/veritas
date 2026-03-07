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

/* Vector and Matrix operations */
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

/* File I/O for Matrices */

Matrix* matrix_load_csv(const char* filepath) {
    FILE* fp = fopen(filepath, "r");
    if (!fp) {
        fprintf(stderr, "Error: Could not open file %s\n", filepath);
        exit(1);
    }

    Matrix* mat = arena_alloc(global_arena, sizeof(Matrix));
    
    // Simple CSV parser: first line is headers
    char line[4096];
    if (!fgets(line, sizeof(line), fp)) {
        fclose(fp);
        return NULL;
    }

    // Count columns
    int cols = 0;
    char* tmp = strdup(line);
    char* token = strtok(tmp, ",\n");
    while (token) {
        cols++;
        token = strtok(NULL, ",\n");
    }
    free(tmp);

    mat->cols = cols;
    mat->column_names = arena_alloc(global_arena, cols * sizeof(char*));
    
    tmp = strdup(line);
    token = strtok(tmp, ",\n");
    for (int i = 0; i < cols; i++) {
        mat->column_names[i] = arena_alloc(global_arena, strlen(token) + 1);
        strcpy(mat->column_names[i], token);
        token = strtok(NULL, ",\n");
    }
    free(tmp);

    // Count rows and load data
    int rows = 0;
    long data_start = ftell(fp);
    while (fgets(line, sizeof(line), fp)) {
        rows++;
    }
    mat->rows = rows;
    mat->data = arena_alloc(global_arena, rows * cols * sizeof(double));

    fseek(fp, data_start, SEEK_SET);
    for (int r = 0; r < rows; r++) {
        fgets(line, sizeof(line), fp);
        token = strtok(line, ",\n");
        for (int c = 0; c < cols; c++) {
            mat->data[r * cols + c] = token ? atof(token) : 0.0;
            token = strtok(NULL, ",\n");
        }
    }

    fclose(fp);
    return mat;
}

Matrix* matrix_load_bin(const char* filepath, int rows, int cols) {
    FILE* fp = fopen(filepath, "rb");
    if (!fp) {
        fprintf(stderr, "Error: Could not open file %s\n", filepath);
        exit(1);
    }

    Matrix* mat = arena_alloc(global_arena, sizeof(Matrix));
    mat->rows = rows;
    mat->cols = cols;
    mat->column_names = NULL;
    mat->data = arena_alloc(global_arena, rows * cols * sizeof(double));

    fread(mat->data, sizeof(double), rows * cols, fp);
    fclose(fp);
    return mat;
}

double* matrix_get_column(Matrix* mat, const char* col_name) {
    if (!mat || !mat->column_names) return NULL;
    int col_idx = -1;
    for (int i = 0; i < mat->cols; i++) {
        if (strcmp(mat->column_names[i], col_name) == 0) {
            col_idx = i;
            break;
        }
    }
    if (col_idx == -1) return NULL;

    double* vec = arena_alloc(global_arena, mat->rows * sizeof(double));
    for (int i = 0; i < mat->rows; i++) {
        vec[i] = mat->data[i * mat->cols + col_idx];
    }
    return vec;
}

double* matrix_get_column_idx(Matrix* mat, int col_idx) {
    if (!mat || col_idx < 0 || col_idx >= mat->cols) return NULL;
    double* vec = arena_alloc(global_arena, mat->rows * sizeof(double));
    for (int i = 0; i < mat->rows; i++) {
        vec[i] = mat->data[i * mat->cols + col_idx];
    }
    return vec;
}

/* Statistics */
double mean(double* data, int n) {
    double sum = 0;
    for (int i = 0; i < n; i++) sum += data[i];
    return sum / n;
}

double standard_deviation(double* data, int n) {
    if (n <= 0) return 0.0;
    double m = mean(data, n);
    double sum_sq = 0;
    for (int i = 0; i < n; i++) sum_sq += (data[i] - m) * (data[i] - m);
    return sqrt(sum_sq / n);
}
