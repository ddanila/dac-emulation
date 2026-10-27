#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*links)(FILE*),(*signals)(FILE*),(*lists)(FILE*),(*graph)(FILE*);
static vpiHandle callbacks[2];static __vpiSignal*signals_native[2];static unsigned stage;
static int(*typed_toggle)(unsigned long long,int);static unsigned long long typed_id;
static char names[2][2]={"a","b"};
static std::string inventory(int(*api)(FILE*)){
 char*p=0;size_t size=0;FILE*f=open_memstream(&p,&size);if(!f)exit(2);
 int result=api(f);if(fclose(f)||result)exit(2);std::string text(p,size);free(p);return text;
}
static void refuse(const char*name){
 if(!links)return;
 char*p=0;size_t size=0;FILE*f=open_memstream(&p,&size);if(!f)exit(2);
 int result=links(f);if(fclose(f)||result!=-1||size)exit(2);free(p);printf("REFUSED %s\n",name);
}
static void snapshot(const char*name){
 if(!links)return;
 auto before=inventory(links);if(inventory(links)!=before)exit(2);
 printf("STATE %s\n%s%s%s%sEND_STATE\n",name,before.c_str(),inventory(signals).c_str(),inventory(lists).c_str(),inventory(graph).c_str());
}
static PLI_INT32 changed(p_cb_data cb){
 if(typed_toggle){if(typed_toggle(typed_id,0)!=-1)exit(2);printf("TYPED_ACTIVE_REFUSED\n");}
 refuse("active-traversal");printf("CALLBACK %s %u\n",cb->user_data,cb->value->value.vector[0].aval);return 0;
}
static PLI_INT32 run(PLI_BYTE8*){
 if(!stage){
  const char*mode=getenv("K7658_REFERENTS");if(!mode)exit(2);
  if(!strcmp(mode,"on")){
   links=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_signal_inventory");
   signals=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_inventory");
   lists=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");
   graph=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_net_inventory");
   if(!links||!signals||!lists||!graph)exit(2);
  }
  for(unsigned i=0;i<2;++i){
   signals_native[i]=dynamic_cast<__vpiSignal*>(vpi_handle_by_name(i?"test.b":"test.a",0));if(!signals_native[i])exit(2);
   s_vpi_time t={};t.type=vpiSuppressTime;s_vpi_value v={};v.format=vpiVectorVal;
   s_cb_data cb={};cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=signals_native[i];cb.user_data=names[i];cb.time=&t;cb.value=&v;
   callbacks[i]=vpi_register_cb(&cb);if(!callbacks[i])exit(2);
  }
  if(links){
   refuse("callbacks-unadmitted");
   auto admit=(unsigned long long(*)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");
   auto handle_admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");if(!admit||!handle_admit)exit(2);
   for(unsigned i=0;i<2;++i)if(!admit(callbacks[i],changed,names[i],signals_native[i]))exit(2);
   refuse("handles-unadmitted");
   for(auto h:signals_native)if(!handle_admit(h))exit(2);
   snapshot("before");auto before=inventory(links);auto a=signals_native[0],b=signals_native[1];
   auto node=a->node;a->node=b->node;refuse("other-node");a->node=node;
   a->node=(vvp_net_t*)1;refuse("foreign-node");a->node=node;
   auto filter=node->fil;node->fil=b->node->fil;refuse("other-filter");node->fil=filter;
   node->fil=(vvp_net_fil_t*)1;refuse("foreign-filter");node->fil=filter;
   auto cb=dynamic_cast<__vpiCallback*>(callbacks[0]);if(!cb)exit(2);auto object=cb->cb_data.obj;
   cb->cb_data.obj=b;refuse("other-object");cb->cb_data.obj=object;
   cb->cb_data.obj=(vpiHandle)1;refuse("foreign-object");cb->cb_data.obj=object;
   if(inventory(links)!=before)exit(2);snapshot("restored");
   typed_toggle=(int(*)(unsigned long long,int))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_toggle");
   typed_id=handle_admit(signals_native[0]);if(!typed_toggle||!typed_id)exit(2);
   for(int field=0;field<6;++field){
    if(typed_toggle(typed_id,field)!=1)exit(2);
    if(typed_toggle(typed_id^0xffff,field)!=-1 || typed_toggle(typed_id,(field+1)%6)!=-1)exit(2);
    printf("TYPED_GUARD %d\n",field);
    char name[40];snprintf(name,sizeof(name),"typed-%d",field);
    if(field<2)snapshot(name);else refuse(name);
    if(typed_toggle(typed_id,field)!=1)exit(2);
    snprintf(name,sizeof(name),"typed-restored-%d",field);snapshot(name);
   }

  }
 }else if(stage==1){snapshot("changed");if(!vpi_remove_cb(callbacks[1]))exit(2);snapshot("cancelled");}
 else if(stage==2)snapshot("deleted");else exit(2);
 printf("DONE %u\n",stage++);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$callback_links";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
