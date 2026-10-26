/* Exercise the real shim's Normal step/input/step contract without an ADC. */
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <math.h>
#include "ngspice/cmtypes.h"
#include "ngspice/cosim.h"

static void *load(const char *path) { return dlopen(path, RTLD_NOW|RTLD_GLOBAL); }
static void output(struct co_info *info, unsigned bit, Digital_t *value)
{
    printf("OUTPUT time=%a bit=%u state=%d strength=%d\n",
           info->vtime, bit, value->state, value->strength);
}
static void advance(struct co_info *info, double target)
{
    for (unsigned i=0; i<100; ++i) {
        info->vtime=target;
        info->step(info);
        printf("RETURN requested=%a returned=%a\n", target, info->vtime);
        if (info->vtime>=target) return;
    }
    fprintf(stderr,"Advance did not reach requested time\n"); exit(3);
}
int main(int argc, char **argv)
{
    if (argc!=7) return 2;
    setbuf(stdout,NULL);
    void *shim=load(argv[1]);
    if (!shim) { fprintf(stderr,"%s\n",dlerror()); return 2; }
    void (*setup)(struct co_info*)=dlsym(shim,"Cosim_setup");
    if (!setup) return 2;
    const char *libs[]={argv[2],argv[3]}, *sim[]={argv[4]};
    struct co_info info={.lib_argc=2,.lib_argv=libs,.sim_argc=1,.sim_argv=sim,
                         .out_fn=output,.dlopen_fn=load};
    double target=strtod(argv[5],NULL), prior=strtod(argv[6],NULL);
    if (!isfinite(target) || !isfinite(prior) || target<=0 || prior<0 || prior>=target) return 2;
    setup(&info);
    if (info.method!=Normal || info.in_count!=1 || info.out_count!=1 || info.inout_count) return 2;
    Digital_t zero={ZERO,STRONG},one={ONE,STRONG};
    info.in_fn(&info,0,&zero);
    if (prior>0) advance(&info,prior);
    advance(&info,target);
    printf("APPLY target=%a\n",target);
    info.in_fn(&info,0,&one);
    advance(&info,target+100e-12);
    info.cleanup(&info);
    return 0;
}
