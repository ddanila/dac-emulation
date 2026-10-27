#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;
 if(r){free(p);return NULL;}return p;
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_mux_inventory");
 int (*toggle)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_mux_toggle");
 const char *mode=getenv("K7658_MUX_PROBE");
 printf("MXM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("MXM_BEFORE\n%sMXM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<5;field++) {
   int found=toggle(field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("MXM_CHANGED %d\n%sMXM_RESTORED\n%sMXM_FAULT %d %d %d\n",field,changed?changed:"",after?after:"",field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("MXM_DONE %u\n",stage++);return 0;
}
static PLI_INT32 changed(p_cb_data unused) {(void)unused;return observe(NULL);}
static PLI_INT32 startup(p_cb_data unused) {
 (void)unused;observe(NULL);
 vpiHandle target=vpi_handle_by_name("mux_probe.out",NULL);if(!target)exit(2);
 static s_vpi_time time={.type=vpiSuppressTime};static s_vpi_value value={.format=vpiSuppressVal};
 s_cb_data cb={0};cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=target;cb.time=&time;cb.value=&value;
 if(!vpi_register_cb(&cb))exit(2);return 0;
}
static PLI_INT32 drive(PLI_BYTE8 *unused) {
 (void)unused;s_vpi_value v={.format=vpiHexStrVal};
 vpiHandle target=vpi_handle_by_name("mux_probe.b",NULL);if(!target)exit(2);
 v.value.str="c3";vpi_put_value(target,&v,NULL,vpiNoDelay);
 target=vpi_handle_by_name("mux_probe.wideb",NULL);if(!target)exit(2);
 v.value.str="ffffffffffffffff0123";vpi_put_value(target,&v,NULL,vpiNoDelay);
 return observe(NULL);
}
static void setup(void) {
 s_cb_data cb={0};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$mux_observe";task.calltf=observe;vpi_register_systf(&task);
 task.tfname="$mux_drive";task.calltf=drive;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
