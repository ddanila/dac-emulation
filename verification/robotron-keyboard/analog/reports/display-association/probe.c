#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
typedef unsigned long long (*lookup_fn)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*);
typedef int (*swap_fn)(const void*,const void*,PLI_INT32(*)(p_cb_data));
static int (*payload)(FILE*),(*association)(FILE*,lookup_fn),(*mutate)(swap_fn);
static int (*family)(FILE*,PLI_BYTE8*,PLI_INT32(*)(p_cb_data));
static lookup_fn lookup;
static swap_fn swap;
static char *payload_text(void) {
 char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);
 if(!f || payload(f) || fclose(f)) exit(2);
 return text;
}
static void snapshot(void) {
 puts("VA_BEGIN");
 if(family(stdout,NULL,NULL) || payload(stdout) || association(stdout,lookup)) exit(2);
 puts("VA_END");
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 void *module=dlopen(getenv("K7658_DISPLAY_MODULE"),RTLD_LAZY|RTLD_NOLOAD);
 if(!module) exit(2);
 payload=dlsym(module,"robotron_display_inventory");
 association=dlsym(module,"robotron_display_associations");
 mutate=dlsym(module,"robotron_display_swap_callback_data");
 family=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_family_inventory");
 lookup=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_payload_identity");
 swap=dlsym(RTLD_DEFAULT,"robotron_vvp_sync_swap_payloads");
 printf("VA_API %d\n",association!=NULL);
 const char *mode=getenv("K7658_DISPLAY_PROBE");
 if(!strcmp(mode,"off")) {dlclose(module);return 0;}
 if(!payload || !association || !mutate || !family || !lookup || !swap) exit(2);
 if(lookup((const void*)1,NULL,NULL)!=0 || swap((const void*)1,(const void*)2,NULL)!=-1) exit(2);
 snapshot();snapshot();
 if(!strcmp(mode,"corrupt")) {
  char *before=payload_text();int changed=mutate(swap);
  if(changed!=0 && changed!=1) exit(2);
  if(changed) {
   char *after=payload_text();FILE *sink=tmpfile();
   if(!sink) exit(2);
   int rejected=association(sink,lookup)==-1;fclose(sink);
   int equal=!strcmp(before,after);free(after);
   if(mutate(swap)!=1) exit(2);
   snapshot();
   printf("VA_FAULT payload_unchanged=%d rejected=%d restored=1\n",equal,rejected);
   if(!equal || !rejected) exit(2);
  } else puts("VA_FAULT none");
  free(before);
 }
 dlclose(module);return 0;
}
static void setup(void) {
 s_vpi_systf_data d={0};d.type=vpiSysTask;d.tfname="$display_inventory";d.calltf=observe;vpi_register_systf(&d);
}
void (*vlog_startup_routines[])(void)={setup,0};
