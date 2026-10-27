#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static unsigned stage;
static char *snapshot(int (*inventory)(FILE*)) {
 char *p=NULL;size_t n=0;FILE *f=open_memstream(&p,&n);if(!f)exit(2);
 int r=inventory(f);
 int (*codes)(FILE*)=dlsym(RTLD_DEFAULT,"robotron_vvp_thread_code_inventory");
 if(!codes || codes(f))r=1;
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
  unsigned long long (*identity)(void*,void**)=dlsym(RTLD_DEFAULT,"robotron_vvp_code_identity");
  unsigned long long thread_id=0,code_id=0;void *pc=0,*opcode=0;
  char *entry=strstr(before,"VTC_THREAD ");
  if(!identity || !entry || sscanf(entry,"VTC_THREAD %llu %p %llu",&thread_id,&pc,&code_id)!=3)exit(2);
  int valid=identity(pc,&opcode)==code_id && code_id && opcode;
  opcode=(void*)(uintptr_t)1;
  int foreign=identity((void*)(uintptr_t)1,&opcode)==0 && !opcode;
  opcode=(void*)(uintptr_t)1;
  int null=identity(0,&opcode)==0 && !opcode;
  opcode=(void*)(uintptr_t)1;
  int misaligned=identity((char*)pc+1,&opcode)==0 && !opcode;
  printf("VTM_ADDRESS valid=%d foreign=%d null=%d misaligned=%d\n",valid,foreign,null,misaligned);
  if(!valid || !foreign || !null || !misaligned)exit(2);
  if(!strcmp(mode,"corrupt")) for(int choice=0;choice<2;choice++) {
   int field=choice?11:3;
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
static void setup(void){
 s_vpi_systf_data t={0};t.type=vpiSysTask;t.tfname="$thread_observe";t.calltf=task;vpi_register_systf(&t);
}
void (*vlog_startup_routines[])(void)={setup,0};
