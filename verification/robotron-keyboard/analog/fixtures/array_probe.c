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
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_array_inventory");
 int (*toggle)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_array_toggle");
 const char *mode=getenv("K7658_ARRAY_PROBE");
 printf("VAM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("VAM_BEFORE\n%sVAM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<4;field++) {
   int found=toggle(field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("VAM_CHANGED %d\n%sVAM_RESTORED\n%sVAM_FAULT %d %d %d\n",field,changed?changed:"",after?after:"",field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("VAM_DONE %u\n",stage++);return 0;
}
static PLI_INT32 cache(PLI_BYTE8 *unused) {
 (void)unused;
 vpiHandle array=vpi_handle_by_name("array_probe.memory",NULL);
 if(!array || !vpi_handle_by_index(array,0))exit(2);
 return 0;
}
static PLI_INT32 quiet_callback(p_cb_data unused) {(void)unused;return 0;}
static PLI_INT32 callback(PLI_BYTE8 *unused) {
 (void)unused;
 s_cb_data cb={0};s_vpi_time time={0};s_vpi_value value={0};
 time.type=vpiSuppressTime;value.format=vpiSuppressVal;
 cb.reason=cbValueChange;cb.cb_rtn=quiet_callback;cb.time=&time;cb.value=&value;
 cb.obj=vpi_handle_by_name("array_probe.memory",NULL);
 if(!cb.obj || !vpi_register_cb(&cb))exit(2);
 return 0;
}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$array_observe";task.calltf=observe;vpi_register_systf(&task);
 task.tfname="$array_cache";task.calltf=cache;vpi_register_systf(&task);
 task.tfname="$array_callback";task.calltf=callback;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
