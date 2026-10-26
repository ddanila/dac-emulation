#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static char identity;
static PLI_INT32 callback(p_cb_data cb);
static void snapshot(int (*family)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data)),int (*executing)(FILE*)) {
 puts("VX_BEGIN");
 if(family(stdout,&identity,callback) || executing(stdout)) exit(2);
 puts("VX_END");
}
static void observe(void) {
 int (*executing)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_executing_inventory");
 printf("VX_API %d\n",executing!=NULL);
 const char *mode=getenv("K7658_WRAPPER_PROBE");
 if(!mode || !strcmp(mode,"off")) return;
 int (*family)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data))=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_family_inventory");
 int (*toggle)(void)=dlsym(RTLD_DEFAULT,"robotron_vvp_executing_toggle_delete");
 unsigned long long (*lookup)(const void*)=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_executing_wrapper");
 if(!executing || !family || !toggle || !lookup || lookup((void*)1)!=0) exit(2);
 snapshot(family,executing);snapshot(family,executing);
 if(!strcmp(mode,"corrupt")) {
  int changed=toggle();printf("VX_FAULT %d\n",changed);
  if(changed!=0 && changed!=1) exit(2);
  if(changed) {
   snapshot(family,executing);
   if(toggle()!=1) exit(2);
   snapshot(family,executing);
  }
 }
}
static PLI_INT32 callback(p_cb_data cb) {
 s_vpi_time now={.type=vpiSimTime};vpi_get_time(NULL,&now);
 printf("CALLBACK %u %u %d %d\n",now.high,now.low,cb->reason,cb->index);
 observe();return 0;
}
static PLI_INT32 schedule(PLI_BYTE8 *unused) {
 (void)unused;
 const int reasons[]={cbAfterDelay,cbReadWriteSynch,cbReadOnlySynch,cbAfterDelay};
 for(int i=0;i<4;i++) {
  s_vpi_time delay={.type=vpiSimTime,.low=i==0?1000:(i==3?2000:0)};
  s_cb_data cb={0};cb.reason=reasons[i];cb.cb_rtn=callback;cb.time=&delay;cb.index=i+1;cb.user_data=&identity;
  vpiHandle handle=vpi_register_cb(&cb);
  if(!handle || (i==3 && !vpi_remove_cb(handle))) exit(2);
 }
 observe();return 0;
}
static PLI_INT32 empty(PLI_BYTE8 *unused) {(void)unused;observe();return 0;}
static void setup(void) {
 s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname="$wrapper_schedule";d.calltf=schedule;vpi_register_systf(&d);
 d.tfname="$wrapper_empty";d.calltf=empty;vpi_register_systf(&d);
}
void (*vlog_startup_routines[])(void)={setup,0};
