#include <stdio.h>
#include "../../engine-patches/mpfr_linear_solver.h"
int main(int argc, char **argv)
{
    if (argc != 2) return 1;
    int bits = atoi(argv[1]), n, count, row, col;
    double value;
    RobotronMpfr solver = {0};
    if (scanf("%d %d", &n, &count) != 2 || count < 1 || count > 1000000 || robotron_mpfr_init(&solver,n,bits)) return 2;
    robotron_mpfr_reset(&solver);
    for (int i = 0; i < count; ++i) {
        if (scanf("%d %d %la", &row, &col, &value) != 3 || col > n || robotron_mpfr_set(&solver,row-1,col-1,value)) return 3;
    }
    for (int i = 0; i < n; ++i)
        if (scanf("%la", &value) != 1 || robotron_mpfr_set(&solver,i,n,value)) return 4;
    double *solution = calloc((size_t)n+1,sizeof(double));
    if (!solution) return 5;
    int status = robotron_mpfr_solve(&solver,solution);
    if (!status) for (int i = 1; i <= n; ++i) printf("%d %a\n", i, solution[i]);
    robotron_mpfr_destroy(&solver); free(solution);
    return status ? 6 : 0;
}
