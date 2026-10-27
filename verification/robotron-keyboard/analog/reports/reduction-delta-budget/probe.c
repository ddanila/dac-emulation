#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/resource.h>
#include <dlfcn.h>
#include <vpi_user.h>
static double now(void) {
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(2);
 return t.tv_sec+t.tv_nsec*1e-9;
}
static PLI_INT32 benchmark(p_cb_data unused) {
 (void)unused;
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_inventory");
 int (*types)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_types");
 int (*reductions)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_inventory");
 int (*reference)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_reference");
 int (*delta)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_reduction_delta_inventory");
 if(!inventory || !types || !reductions || !reference || !delta)exit(2);
 FILE *out=fopen("before.txt","w");
 if(!out || inventory(out) || fclose(out))exit(2);
 out=fopen("types-before.txt","w");if(!out || types(out) || fclose(out))exit(2);
 out=fopen("reduction-before.txt","w");if(!out || reductions(out) || fclose(out))exit(2);
 out=fopen("reduction-reference.txt","w");if(!out || reference(out) || fclose(out))exit(2);
 out=fopen("reduction-delta-before.txt","w");if(!out || delta(out) || fclose(out))exit(2);
 out=fopen("/dev/null","w");if(!out)exit(2);
 double sum=0,minimum=1e99,maximum=0;
 for(int i=0;i<64;i++) {
  double start=now();if(delta(out) || fflush(out))exit(2);
  double elapsed=now()-start;sum+=elapsed;
  if(elapsed<minimum)minimum=elapsed;if(elapsed>maximum)maximum=elapsed;
 }
 if(fclose(out))exit(2);
 out=fopen("after.txt","w");
 if(!out || inventory(out) || fclose(out))exit(2);
 out=fopen("types-after.txt","w");if(!out || types(out) || fclose(out))exit(2);
 out=fopen("reduction-after.txt","w");if(!out || reductions(out) || fclose(out))exit(2);
 out=fopen("reduction-delta-after.txt","w");if(!out || delta(out) || fclose(out))exit(2);
 int (*arrays)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");
 int (*operands)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_code_operand_reference");
 if(!arrays || !operands)exit(2);
 out=fopen("arrays.txt","w");if(!out || arrays(out) || fclose(out))exit(2);
 out=fopen("operands.txt","w");if(!out || operands(out) || fclose(out))exit(2);
 printf("NET_BUDGET 64 %.9f %.9f %.9f\n",sum,minimum,maximum);
 struct rusage usage;if(getrusage(RUSAGE_SELF,&usage))exit(2);
 printf("NET_RSS %ld\n",usage.ru_maxrss);
 printf("NET_BUDGET_DONE\n");
 /* No firmware execution: this measures the compiled profile only. */
 vpi_control(vpiFinish,0);return 0;
}
static void setup(void) {
 s_cb_data cb={0};cb.reason=cbStartOfSimulation;cb.cb_rtn=benchmark;
 if(!vpi_register_cb(&cb))exit(2);
}
void (*vlog_startup_routines[])(void)={setup,0};
