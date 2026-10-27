#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*);
static unsigned callbacks;static PLI_BYTE8 caller;
static PLI_INT32 changed(p_cb_data cb){++callbacks;printf("CALLBACK %d\n",cb->value->value.vector[0].aval);return 0;}
static int integer(vpiHandle h){s_vpi_value v={};v.format=vpiIntVal;vpi_get_value(h,&v);return v.value.integer;}
static std::string snapshot(){
 if(!inventory)return "";
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f)||rc)exit(2);std::string s(p,n);free(p);return s;
}
static void unchanged(const char*field,const std::string&before){
 if(inventory){auto after=snapshot();if(after!=before)exit(2);printf("IMAGE %s\n%s",field,after.c_str());}
}
static PLI_INT32 run(PLI_BYTE8*){
 auto a=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.left",0));
 auto b=dynamic_cast<__vpiSignal*>(vpi_handle_by_name("test.right",0));
 if(!a||!b||a->is_netarray||b->is_netarray||a->bits||b->bits)exit(2);
 s_vpi_time tm={};tm.type=vpiSuppressTime;s_vpi_value val={};val.format=vpiVectorVal;
 s_cb_data cb={};cb.reason=cbValueChange;cb.cb_rtn=changed;cb.obj=a;cb.time=&tm;cb.value=&val;cb.user_data=&caller;
 vpiHandle handle=vpi_register_cb(&cb);if(!handle)exit(2);
 const char*mode=getenv("K7658_REFERENTS");if(!mode)exit(2);
 if(!strcmp(mode,"on")){
  inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");
  auto admit=(unsigned long long(*)(vpiHandle,PLI_INT32(*)(p_cb_data),void*,vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");
  if(!inventory||!admit||!admit(handle,changed,&caller,a))exit(2);
 }
 auto before=snapshot();if(inventory)printf("IMAGE before\n%s",before.c_str());printf("BASE %d\n",integer(a));
 auto node=a->node;a->node=b->node;printf("NODE %d\n",integer(a));unchanged("node",before);a->node=node;
 auto sign=a->signed_flag;a->signed_flag=0;printf("SIGNED %d\n",integer(a));unchanged("signed",before);a->signed_flag=sign;
 auto msb=a->msb;auto lsb=a->lsb;a->msb=lsb;a->lsb=msb;
 printf("RANGE %d %d\n",integer(vpi_handle(vpiLeftRange,a)),integer(vpi_handle(vpiRightRange,a)));unchanged("range",before);a->msb=msb;a->lsb=lsb;
 if(snapshot()!=before||integer(a)!=-6||callbacks)exit(2);printf("RESTORED -6\n");
 auto bit=vpi_handle_by_index(a,0);if(!bit||!a->bits||vpi_handle_by_index(a,0)!=bit)exit(2);
 printf("BIT %d\n",integer(bit));unchanged("bit-cache",before);
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$referents";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
