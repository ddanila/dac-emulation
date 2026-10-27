#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*),(*admitted_inventory)(FILE*);static unsigned round_id;
static int integer(vpiHandle h){s_vpi_value v={};v.format=vpiIntVal;vpi_get_value(h,&v);return v.value.integer;}
static std::string scan(int(*fn)(FILE*),bool refuse=false){
 if(!fn)return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=fn(f);if(fclose(f))exit(2);std::string s(p,n);free(p);
 if(refuse?(rc>=0||n):rc!=0)exit(2);return s;
}
static void image(const char*label){if(inventory)printf("IMAGE %s%u\n%s%sIMAGE_END\n",label,round_id,scan(inventory).c_str(),scan(admitted_inventory).c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 auto visible=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.visible",0));
 auto hidden=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.hidden",0));
 if(!visible||!hidden||hidden->is_netarray||integer(hidden)!=-6)exit(2);
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(!strcmp(mode,"on")&&!inventory){
  auto admit=(unsigned long long(*)(vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_admit");
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_signal_inventory");
  admitted_inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_signal_handle_inventory");
  if(!inventory||!admitted_inventory||!admit||!admit(visible))exit(2);
 }
 ++round_id;printf("ROUND %u\n",round_id);auto before=scan(inventory);auto admitted_before=scan(admitted_inventory);image("before");
 hidden->signed_flag=0;if(integer(hidden)!=10)exit(2);printf("SIGNAL -6 10\n");
 if(inventory&&(scan(inventory)==before||scan(admitted_inventory)!=admitted_before))exit(2);image("signed");hidden->signed_flag=1;
 int left=hidden->msb.get_value();hidden->msb.set_value(left+1);image("range");hidden->msb.set_value(left);
 if(scan(inventory)!=before)exit(2);image("restored");
 auto bit=vpi_handle_by_index(hidden,0);if(!bit||integer(bit)!=0||!hidden->bits)exit(2);
 image("cached");auto cached=scan(inventory);if(inventory&&round_id==1&&cached==before)exit(2);
 if(inventory){
  auto refuse=[&](const char*label){scan(inventory,true);printf("REFUSED %s\n",label);};
  auto node=hidden->node;hidden->node=(vvp_net_t*)1;refuse("node");hidden->node=node;
  auto scope=hidden->within.scope;hidden->within.scope=(__vpiScope*)1;refuse("scope");hidden->within.scope=scope;
  auto name=hidden->id.name;hidden->id.name=(const char*)1;refuse("name");hidden->id.name=name;
  hidden->is_netarray=1;refuse("array-arm");hidden->is_netarray=0;
  auto bits=hidden->bits;hidden->bits=(__vpiBit*)1;refuse("cache");hidden->bits=bits;
  auto index=bits[0].index;bits[0].index=(vpiHandle)1;refuse("bit-index");bits[0].index=index;
  auto parent=(bits-1)->parent;(bits-1)->parent=visible;refuse("bit-parent");(bits-1)->parent=parent;
  auto base=bits[0].bit0;bits[0].bit0=(__vpiBit*)1;refuse("bit-base");bits[0].bit0=base;
  auto owner=hidden->within.scope;auto members=owner->intern;
  for(auto i=owner->intern.begin();i!=owner->intern.end();++i)if(*i==hidden){owner->intern.erase(i);break;}
  refuse("missing-owner");owner->intern=members;
  owner->intern.push_back(hidden);refuse("duplicate-owner");owner->intern=members;
  if(scan(inventory)!=cached||scan(admitted_inventory)!=admitted_before)exit(2);
 }
 if(inventory){
  auto toggle=(int(*)(unsigned))dlsym(RTLD_DEFAULT,"robotron_vvp_scope_signal_toggle");if(!toggle||toggle(6)!=-1)exit(2);
  for(unsigned field=0;field<6;++field){
   if(toggle(field)!=1||toggle((field+1)%6)!=-1)exit(2);
   auto changed=scan(inventory,field>=2);
   if(field<2&&changed==cached)exit(2);
   if(scan(admitted_inventory)!=admitted_before||toggle(field)!=1||scan(inventory)!=cached)exit(2);
   printf("TOGGLE %u %u restored\n",round_id,field);
  }
 }
 image("cached-restored");printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$scope_signals";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
