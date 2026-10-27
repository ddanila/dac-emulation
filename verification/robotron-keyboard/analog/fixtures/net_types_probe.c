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
 if(r){free(p);return NULL;}
 int (*types)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_types");
 if(!types || types(stdout))exit(2);
 return p;
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_inventory");
 int (*toggle)(int)=dlsym(RTLD_DEFAULT,"robotron_vvp_net_toggle");
 const char *mode=getenv("K7658_NET_PROBE");
 printf("VNM_API %u %d\n",stage,inventory!=NULL);
 if(mode && strcmp(mode,"off")) {
  if(!inventory || !toggle)exit(2);
  char *before=snapshot(inventory),*repeat=snapshot(inventory);
  if(!before || !repeat || strcmp(before,repeat))exit(2);
  printf("VNM_BEFORE\n%sVNM_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt"))for(int field=0;field<6;field++) {
   int found=toggle(field);if(found!=0 && found!=1)exit(2);
   if(!found)continue;
   char *changed=snapshot(inventory);
   if(toggle(field)!=1)exit(3);
   char *after=snapshot(inventory);
   int detected=changed && strcmp(before,changed)!=0;
   int restored=after && !strcmp(before,after);
   printf("VNM_CHANGED %d\n%sVNM_RESTORED\n%sVNM_FAULT %d %d %d\n",field,changed?changed:"",after?after:"",field,detected,restored);
   free(changed);free(after);if(!detected || !restored)exit(2);
  }
  free(before);
 }
 printf("VNM_DONE %u\n",stage++);return 0;
}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$net_observe";task.calltf=observe;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
