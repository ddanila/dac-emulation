/* Frozen-system diagnostic using the same Sparse library as the audited runtime. */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "ngspice/spmatrix.h"

int main(void)
{
    int n, count, error, row, col;
    double value;
    if (scanf("%d %d", &n, &count) != 2 || n < 1 || n > 5000 || count < 1 || count > n*n)
        return 2;
    MatrixPtr matrix = spCreate(n, 0, &error);
    if (!matrix || error) return 3;
    double *rhs = calloc((size_t)n+1, sizeof(double));
    double *solution = calloc((size_t)n+1, sizeof(double));
    if (!rhs || !solution) return 4;
    for (int i = 0; i < count; ++i) {
        if (scanf("%d %d %la", &row, &col, &value) != 3 || row < 1 || row > n || col < 1 || col > n || !isfinite(value))
            return 5;
        *spGetElement(matrix, row, col) = value;
    }
    for (int i = 1; i <= n; ++i)
        if (scanf("%la", &rhs[i]) != 1 || !isfinite(rhs[i])) return 6;
    spMNA_Preorder(matrix);
    error = spOrderAndFactor(matrix, NULL, .001, 1e-13, 1);
    if (error) {
        fprintf(stderr, "Sparse factorization error: %d\n", error);
        return 7;
    }
    spSolve(matrix, rhs, solution, NULL, NULL);
    for (int i = 1; i <= n; ++i) {
        if (!isfinite(solution[i])) return 8;
        printf("%d %a\n", i, solution[i]);
    }
    spDestroy(matrix);
    free(rhs);
    free(solution);
    return 0;
}
