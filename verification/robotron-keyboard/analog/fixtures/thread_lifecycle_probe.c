#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);
 int (*queue)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_thread_queue_inventory");
 if(!queue || queue(f))r=1;
 if(fclose(f))r=1;if(r){free(p);return NULL;}return p;
}
static void observe(void) {
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_thread_compact_inventory");
 int (*toggle)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_thread_toggle");
 const char *mode=getenv("K7658_THREAD_PROBE");
 printf("VTM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("VTM_BEFORE\n%sVTM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) for(int field=8;field<11;field++) {
   int present=toggle(field);if(present!=0 && present!=1)exit(2);
   if(present) {
    char *changed=snapshot(inventory);
    if(toggle(field)!=1)exit(3);
    char *after=snapshot(inventory);
    int detected=changed && strcmp(before,changed)!=0;
    int restored=after && !strcmp(before,after);
    printf("VTM_CHANGED %d\n%sVTM_RESTORED\n%s",field,changed?changed:"",after?after:"");
    printf("VTM_FAULT %d %d %d\n",field,detected,restored);
    free(changed);free(after);if(!detected || !restored)exit(2);
   }
  }
  free(before);
 }
 printf("VTM_DONE %u\n",stage++);
}
static PLI_INT32 task(PLI_BYTE8 *unused) {(void)unused;observe();return 0;}
static PLI_INT32 deferred(p_cb_data cb) {(void)cb;printf("DEFER_CALLBACK\n");observe();return 0;}
static PLI_INT32 defer_task(PLI_BYTE8 *unused) {
 (void)unused;s_vpi_time time={0};time.type=vpiSimTime;
 s_cb_data cb={0};cb.reason=cbReadWriteSynch;cb.cb_rtn=deferred;cb.time=&time;
 if(!vpi_register_cb(&cb))exit(2);return 0;
}
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$thread_observe";t.calltf=task;vpi_register_systf(&t);
 t.tfname="$lifecycle_defer";t.calltf=defer_task;vpi_register_systf(&t);
}
void (*vlog_startup_routines[])(void)={setup,0};
