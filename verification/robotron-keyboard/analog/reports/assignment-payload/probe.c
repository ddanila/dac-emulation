#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);if(fclose(f))r=1;if(r){free(p);return NULL;}return p;
}
static void observe(void) {
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_inventory");
 int (*toggle)(int,int)=dlsym(RTLD_DEFAULT,"robotron_vvp_assignment_toggle");
 const char *mode=getenv("K7658_ASSIGNMENT_PROBE");
 printf("VAM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("VAM_BEFORE\n%sVAM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) for(int kind=4;kind<=8;kind+=4) for(int field=0;field<3;field++) {
   int present=toggle(kind,field);if(present!=0 && present!=1)exit(2);
   if(present) {
    char *changed=snapshot(inventory);
    if(toggle(kind,field)!=1)exit(3);
    char *after=snapshot(inventory);
    int detected=changed && strcmp(before,changed)!=0;
    int restored=after && !strcmp(before,after);
    printf("VAM_CHANGED %d %d\n%sVAM_RESTORED\n%s",kind,field,changed?changed:"",after?after:"");
    printf("VAM_FAULT %d %d %d %d\n",kind,field,detected,restored);
    free(changed);free(after);if(!detected || !restored)exit(2);
   }
  }
  free(before);
 }
 printf("VAM_DONE %u\n",stage++);
}
static PLI_INT32 start(p_cb_data unused){(void)unused;observe();return 0;}
static PLI_INT32 task(PLI_BYTE8 *unused){(void)unused;observe();return 0;}
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$assignment_observe";t.calltf=task;vpi_register_systf(&t);
 s_cb_data cb={0};cb.reason=cbStartOfSimulation;cb.cb_rtn=start;vpi_register_cb(&cb);
}
void (*vlog_startup_routines[])(void)={setup,0};
