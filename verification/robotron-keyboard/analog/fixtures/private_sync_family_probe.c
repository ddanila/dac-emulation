#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <string.h>
#include <vpi_user.h>
static char identity;
static PLI_INT32 callback(p_cb_data cb);
static void observe(void) {
 const char *mode=getenv("K7658_FAMILY_PROBE");
 int (*inventory)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data))=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_family_inventory");
 printf("VF_API %d\n",inventory!=NULL);
 if(inventory) {
  int (*legacy)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data))=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_inventory");
  FILE *sink=tmpfile();
  if(!legacy || !sink || legacy(sink,&identity,callback)!=-1) exit(2);
  fclose(sink);
 }
 if (!mode || !strcmp(mode,"off")) return;
 int (*toggle)(void)=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_toggle_queued_mode");
 if (!inventory || !toggle) exit(2);
 if(inventory(stdout,&identity,callback) || inventory(stdout,&identity,callback)) exit(2);
 if(!strcmp(mode,"corrupt")) {
  int changed=toggle();printf("VF_FAULT %d\n",changed);
  if(changed!=0 && changed!=1) exit(2);
  if(changed && (inventory(stdout,&identity,callback) || toggle()!=1 || inventory(stdout,&identity,callback))) exit(2);
 }
}
static PLI_INT32 callback(p_cb_data cb) {
 s_vpi_time t={.type=vpiSimTime};vpi_get_time(NULL,&t);
 printf("CALLBACK %u %u %d\n",t.high,t.low,cb->index);
 observe();return 0;
}
static PLI_INT32 call(PLI_BYTE8 *unused) {
 (void)unused;
 for(unsigned i=1;i<=3;i++) {
  s_vpi_time delay={.type=vpiSimTime,.low=i*1000};
  s_cb_data cb={0};cb.reason=cbAfterDelay;cb.cb_rtn=callback;cb.time=&delay;
  cb.user_data=&identity;cb.index=i;
  vpiHandle handle=vpi_register_cb(&cb);
  if(!handle || (i==2 && !vpi_remove_cb(handle))) exit(2);
 }
 observe();return 0;
}
static void setup(void) {
 s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname="$queue_inventory";d.calltf=call;vpi_register_systf(&d);
}
void (*vlog_startup_routines[])(void)={setup,0};
