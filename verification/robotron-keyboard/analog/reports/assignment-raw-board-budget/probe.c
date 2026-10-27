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
 int (*assignment_raw)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_raw_inventory");
 int (*queue)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_queue_inventory");

 int (*legacy)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_inventory");
 if(!inventory || !types || !assignment_raw || !queue || !legacy)exit(2);
 FILE *out=fopen("before.txt","w");
 if(!out || inventory(out) || fclose(out))exit(2);
 out=fopen("types-before.txt","w");if(!out || types(out) || fclose(out))exit(2);
 out=fopen("assignment-legacy-before.txt","w");if(!out || legacy(out) || fclose(out))exit(2);
 out=fopen("queue-before.txt","w");if(!out || queue(out) || fclose(out))exit(2);
 out=fopen("assignment_raw-before.txt","w");if(!out || assignment_raw(out) || fclose(out))exit(2);
 out=fopen("/dev/null","w");if(!out)exit(2);
 double sum=0,minimum=1e99,maximum=0;
 for(int i=0;i<64;i++) {
  double start=now();if(assignment_raw(out) || fflush(out))exit(2);
  double elapsed=now()-start;sum+=elapsed;
  if(elapsed<minimum)minimum=elapsed;if(elapsed>maximum)maximum=elapsed;
 }
 if(fclose(out))exit(2);
 out=fopen("after.txt","w");
 if(!out || inventory(out) || fclose(out))exit(2);
 out=fopen("types-after.txt","w");if(!out || types(out) || fclose(out))exit(2);
 out=fopen("assignment-legacy-after.txt","w");if(!out || legacy(out) || fclose(out))exit(2);
 out=fopen("queue-after.txt","w");if(!out || queue(out) || fclose(out))exit(2);
 out=fopen("assignment_raw-after.txt","w");if(!out || assignment_raw(out) || fclose(out))exit(2);
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
