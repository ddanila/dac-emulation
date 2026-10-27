#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <dlfcn.h>
#include <vpi_user.h>
#include "vpi_priv.h"
#include "vvp_net.h"
static unsigned stage;static const char*mode;
static char* snapshot(int*result,size_t*size){
 auto api=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
 char*p=0;*size=0;FILE*f=open_memstream(&p,size);if(!f)exit(2);*result=api(f);if(fclose(f))exit(2);return p;
}
static PLI_INT32 inspect(PLI_BYTE8*){
 if(!mode){mode=getenv("K7658_CALLBACK_WORDS");if(!mode)exit(2);}
 printf("WORD_STAGE %u\n",stage);
 if(strcmp(mode,"off")) {
  if(!stage){
   for(auto name:{"words","aliases"}) {
    char path[32];snprintf(path,sizeof(path),"probe.%s",name);
    auto array=dynamic_cast<__vpiArray*>(vpi_handle_by_name(path,0));if(!array)exit(2);
    printf("WORD_ARRAY %s %p %d\n",name,(void*)array,vpi_get(vpiSize,array));
    for(unsigned i=0;i<array->get_size();i++) {
     auto sig=dynamic_cast<__vpiSignal*>(vpi_handle_by_index(array,i));
     if(!sig || !sig->node || !sig->node->fil)exit(2);
     printf("WORD_SOURCE %s %u %p\n",name,i,(void*)static_cast<vvp_vpi_callback*>(sig->node->fil));
    }
   }
  }
  int r;size_t n;auto before=snapshot(&r,&n);if(r)exit(2);auto repeat=snapshot(&r,&n);if(r || strcmp(before,repeat))exit(2);
  printf("WORD_BEFORE\n%sWORD_REPEAT\n%s",before,repeat);free(repeat);
  if(!strcmp(mode,"corrupt")) {
   auto toggle=(int(*)(unsigned long long,int))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_word_toggle");if(!toggle)exit(2);
   std::vector<unsigned long long>ids;char*copy=strdup(before);char*save=0;
   for(char*line=strtok_r(copy,"\n",&save);line;line=strtok_r(0,"\n",&save)){unsigned long long id;if(sscanf(line,"VCL_WORD %llu",&id)==1)ids.push_back(id);}free(copy);
   for(auto id:ids)for(int field=0;field<3;field++) {
    if(toggle(id,field)!=1)exit(2);auto changed=snapshot(&r,&n);
    if(field==2?(r!=-1 || n):(r || !strcmp(before,changed)))exit(2);
    printf("WORD_FAULT %llu %d %d\n%s",id,field,r,changed);free(changed);
    if(toggle(id,field)!=1)exit(2);auto restored=snapshot(&r,&n);if(r || strcmp(before,restored))exit(2);printf("WORD_RESTORED\n%s",restored);free(restored);
   }
  }
  free(before);
 }
 printf("WORD_DONE %u\n",stage++);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$word_inspect";t.calltf=inspect;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
