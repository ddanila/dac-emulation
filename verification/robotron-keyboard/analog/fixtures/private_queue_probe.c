#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <string.h>
#include <vpi_user.h>
static PLI_INT32 callback(p_cb_data cb) {
 (void)cb;s_vpi_time t={.type=vpiSimTime};vpi_get_time(NULL,&t);
 printf("CALLBACK %u %u\n",t.high,t.low);return 0;
}
static PLI_INT32 call(PLI_BYTE8 *unused) {
 (void)unused;
 s_vpi_time delay={.type=vpiSimTime,.low=1000};
 s_cb_data cb={0};cb.reason=cbAfterDelay;cb.cb_rtn=callback;cb.time=&delay;
 if (!vpi_register_cb(&cb)) {fprintf(stderr,"Missing scheduled callback\n");exit(2);}
 const char *mode=getenv("K7658_QUEUE_PROBE");
 int (*observe)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_queue_inventory");
 printf("VQ_API %d\n",observe!=NULL);
 if (!mode || !strcmp(mode,"off")) return 0;
 if (!observe) {fprintf(stderr,"Missing queue observer\n");exit(2);}
 if (!strcmp(mode,"corrupt")) {
  int (*adjust)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_queue_adjust_first_future");
  if (!adjust || observe(stdout) || adjust(1)!=1 || observe(stdout) || adjust(-1)!=1 || observe(stdout)) {
   fprintf(stderr,"Queue fault control failed\n");exit(2);
  }
 } else for(int i=0;i<2;i++) if(observe(stdout)) {fprintf(stderr,"Queue inventory failed\n");exit(2);}
 return 0;
}
static void setup(void) {
 s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname="$queue_inventory";d.calltf=call;vpi_register_systf(&d);
}
void (*vlog_startup_routines[])(void)={setup,0};
