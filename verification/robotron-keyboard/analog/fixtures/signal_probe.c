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
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_signal_inventory");
 int (*toggle)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_signal_toggle");
 const char *mode=getenv("K7658_SIGNAL_PROBE");
 printf("SGM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("SGM_BEFORE\n%sSGM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<5;field++) {
   int found=toggle(field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("SGM_CHANGED %d\n%sSGM_RESTORED\n%sSGM_FAULT %d %d %d\n",field,changed?changed:"",after?after:"",field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("SGM_DONE %u\n",stage++);return 0;
}
static PLI_INT32 startup(p_cb_data unused) {
 (void)unused;const char* mode=getenv("K7658_SIGNAL_PROBE");
 if(mode && strcmp(mode,"off")) {
  int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_signal_inventory");
  if(!inventory)exit(2);
  char *first=snapshot(inventory),*second=snapshot(inventory);
  if(!first || !second || strcmp(first,second))exit(2);
  printf("SGM_STARTUP\n%sSGM_STARTUP_REPEAT\n%sSGM_STARTUP_END\n",first,second);
  free(first);free(second);
 }
 return 0;
}
static void setup(void) {
 s_cb_data cb={0};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(2);
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$signal_observe";task.calltf=observe;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
