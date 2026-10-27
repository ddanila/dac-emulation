#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
#include "scope_compare.h"
static unsigned stage;
static int(*inventory)(FILE*);
static unsigned long long(*admit)(vpiHandle);
static __vpiSignal*handles[7];
static const char*names[]={"r","n","number","wide","negative","single","late"};
static unsigned long long ids[7];
static std::string snapshot(){
 if(!inventory)return "";
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f)||rc)exit(2);std::string result(p,n);free(p);return result;
}
static int integer(vpiHandle h){s_vpi_value v={};v.format=vpiIntVal;vpi_get_value(h,&v);return v.value.integer;}
static void bind(unsigned i){
 if(admit){ids[i]=admit(handles[i]);if(!ids[i]||admit(handles[i])!=ids[i])exit(2);printf("BIND %s %llu %p\n",names[i],ids[i],(void*)handles[i]);}
}
static void refused(){
 if(!admit)return;
 auto before=snapshot();
 auto array=vpi_handle_by_name("test.netarr",0);if(!array)exit(2);
 vpiHandle candidates[]={vpi_handle_by_name("test.two",0),vpi_handle_by_name("test.real_value",0),array,vpi_handle_by_index(array,0),vpi_handle(vpiLeftRange,handles[0]),0,(vpiHandle)1};
 const char*labels[]={"two-state","real","array","array-word","constant","null","foreign"};
 for(unsigned i=0;i<7;++i){if(i<5&&!candidates[i])exit(2);if(admit(candidates[i]))exit(2);printf("REJECT %u %s\n",stage,labels[i]);}
 if(snapshot()!=before)exit(2);
}
static PLI_INT32 run(PLI_BYTE8*){
 if(stage==0){
  const char*mode=getenv("K7658_REFERENTS");if(!mode)exit(2);
  if(!strcmp(mode,"on")){
   inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_inventory");
   admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");
   if(!inventory||!admit)exit(2);
  }
  for(unsigned i=0;i<6;++i){std::string name=std::string("test.")+names[i];handles[i]=dynamic_cast<__vpiSignal*>(vpi_handle_by_name(name.c_str(),0));if(!handles[i]||handles[i]->bits)exit(2);bind(i);}
  refused();
 }
 if(stage==2){handles[6]=dynamic_cast<__vpiSignal*>(vpip_make_net4(handles[0]->within.scope,"late",3,0,false,handles[0]->node));if(!handles[6]||handles[6]->bits)exit(2);bind(6);}
 if(stage==1||stage==3){
  unsigned first=stage==1?0:6,last=stage==1?6:7;
  for(unsigned i=first;i<last;++i){
   auto h=handles[i];int left=h->msb.get_value(),right=h->lsb.get_value();
   if(i==2){if(vpi_handle_by_index(h,left)||vpi_handle_by_index(h,right)||h->bits)exit(2);printf("NO_BITS %u number\n",stage);continue;}
   auto a=vpi_handle_by_index(h,left),b=vpi_handle_by_index(h,right);
   if(!a||!b||a!=vpi_handle_by_index(h,left)||b!=vpi_handle_by_index(h,right))exit(2);
   printf("ENDS %u %s %d %d\n",stage,names[i],integer(a),integer(b));
  }
 }
 if(stage==3)refused();
 unsigned count=stage<2?6:7;
 for(unsigned i=0;i<count;++i){s_vpi_value v={};v.format=vpiBinStrVal;vpi_get_value(handles[i],&v);printf("VALUE %u %s %s\n",stage,names[i],v.value.str);}
 if(inventory){auto before=snapshot();if(snapshot()!=before)exit(2);printf("IMAGE %u\n%s",stage,before.c_str());}
 printf("DONE %u\n",stage++);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$handle_families";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
