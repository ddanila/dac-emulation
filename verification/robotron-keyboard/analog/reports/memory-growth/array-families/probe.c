#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <vpi_user.h>
static PLI_INT32 check(PLI_BYTE8 *unused) {
 (void)unused;
 const char *family=getenv("K7658_ARRAY_FAMILY");
 vpiHandle other=vpi_handle_by_name("array_family.other",NULL);
 if(!family || !other || vpi_get(vpiSize,other)!=4)exit(2);
 vpiHandle word=vpi_handle_by_index(other,0);if(!word)exit(2);
 s_vpi_value v={0};v.format=vpiIntVal;
 if(!strcmp(family,"alias")) {
  vpiHandle mem=vpi_handle_by_name("array_family.memory",NULL);
  vpiHandle original=vpi_handle_by_index(mem,0);if(!original)exit(2);
  vpi_get_value(word,&v);if(v.value.integer!=0xa5)exit(2);
  v.value.integer=0x5a;vpi_put_value(word,&v,NULL,vpiNoDelay);
  vpi_get_value(original,&v);if(v.value.integer!=0x5a)exit(2);
  v.value.integer=0xa5;vpi_put_value(original,&v,NULL,vpiNoDelay);
  vpi_get_value(word,&v);if(v.value.integer!=0xa5)exit(2);
 }else if(!strcmp(family,"real")) {
  v.format=vpiRealVal;vpi_get_value(word,&v);if(v.value.real!=1.5)exit(2);
 }else if(!strcmp(family,"string")) {
  v.format=vpiStringVal;vpi_get_value(word,&v);if(strcmp(v.value.str,"array"))exit(2);
 }else if(!strcmp(family,"net")) {
  vpi_get_value(word,&v);if(v.value.integer!=0xa5)exit(2);
 }else exit(2);
 printf("FAMILY_PRESENT %s\n",family);return 0;
}
static PLI_INT32 observe(PLI_BYTE8 *unused) {
 (void)unused;
 const char *mode=getenv("K7658_ARRAY_MODE");
 if(!mode)exit(2);
 if(!strcmp(mode,"off"))return 0;
 const char *symbol=!strcmp(mode,"dense")?"robotron_vvp_array_inventory":"robotron_vvp_array_compact_inventory";
 int (*inventory)(FILE*)=dlsym(RTLD_DEFAULT,symbol);if(!inventory)exit(2);
 char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)exit(2);
 int result=inventory(f);if(fclose(f))exit(2);
 if(result==0 || size){free(text);exit(3);}
 free(text);printf("ARRAY_REFUSED %s\n",mode);exit(2);
}
static void setup(void) {
 s_vpi_systf_data task={0};task.type=vpiSysTask;task.tfname="$family_check";task.calltf=check;vpi_register_systf(&task);
 task.tfname="$family_observe";task.calltf=observe;vpi_register_systf(&task);
}
void (*vlog_startup_routines[])(void)={setup,0};
