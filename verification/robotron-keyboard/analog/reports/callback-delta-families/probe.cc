#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
static int compact_ready;
static void compact_refused(int(*api)(FILE*))
{
 char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int r=api(f);if(fclose(f)||r!=-1||n)exit(2);free(p);
}
static void compact_check(int dense_result)
{
 int(*reference)(FILE*)=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_reference");
 int(*delta)(FILE*)=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_delta_inventory");
 if(!reference||!delta)exit(2);
 if(dense_result){compact_refused(compact_ready?delta:reference);puts("VLD_REFUSED_EMPTY");return;}
 if(!compact_ready){
  compact_refused(delta);if(reference(stdout))exit(2);compact_ready=1;
  compact_refused(reference);puts("VLD_INIT_GUARDS");
 }
 if(delta(stdout))exit(2);
}

#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <vpi_user.h>
#include "vvp_net_sig.h"
static const char *family,*timing,*mode;static unsigned stage,drive;static bool foreign_present;
static vpiHandle foreign_object,foreign_callback,known_object,known_callback;
static char known_user='K',foreign_user='F';
class ExtraWire:public vvp_wire_vec4 {
 bool invert_=true;
 public:
 static void* operator new(size_t n){return ::operator new(n);}
 static void operator delete(void*p){::operator delete(p);}
 ExtraWire():vvp_wire_vec4(1,BIT4_0){}
 void get_value(s_vpi_value* value) override {vvp_wire_vec4::get_value(value);if(invert_ && value->format==vpiScalarVal)value->value.scalar=value->value.scalar==vpi0?vpi1:vpi0;}
};
static ExtraWire* extra;
static bool observing(){return !strcmp(mode,"observe");}
static void observe(){
 if(!observing())return;
 auto api=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_inventory");if(!api)exit(2);
 char*text=0;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)exit(2);int result=api(f);if(fclose(f))exit(2);compact_check(result);
 printf("FAM_STAGE %u %d\n",stage++,result);
 if(foreign_present){if(result!=-1||size)exit(2);puts("FAM_REFUSED_EMPTY");}
 else {if(result || !size)exit(2);fwrite(text,1,size,stdout);}
 free(text);
}
static PLI_INT32 callback(p_cb_data cb){
 s_vpi_time time={};time.type=vpiSimTime;vpi_get_time(0,&time);
 int index=*cb->user_data=='F' && !strcmp(family,"array")?cb->index:-1;
 printf("VALUE %u %c %d %d %d\n",time.low,*cb->user_data,cb->value->value.vector[0].aval,cb->value->value.vector[0].bval,index);return 0;
}
static vpiHandle watch(vpiHandle object,char*user){
 s_vpi_time time={};time.type=vpiSuppressTime;s_vpi_value value={};value.format=vpiVectorVal;s_cb_data cb={};
 cb.reason=cbValueChange;cb.cb_rtn=callback;cb.obj=object;cb.time=&time;cb.value=&value;cb.user_data=user;
 vpiHandle handle=vpi_register_cb(&cb);if(!handle)exit(2);return handle;
}
static unsigned long long admit(vpiHandle handle,char*user,vpiHandle object){
 auto api=(unsigned long long(*)(const void*,PLI_INT32(*)(p_cb_data),PLI_BYTE8*,vpiHandle))dlsym(RTLD_DEFAULT,"robotron_vvp_callback_list_admit");if(!api)exit(2);return api(handle,callback,user,object);
}
static void install(){
 foreign_present=true;
 if(!strcmp(family,"owner"))extra=new ExtraWire;
 else {foreign_callback=watch(foreign_object,&foreign_user);if(observing() && admit(foreign_callback,&foreign_user,foreign_object)!=0)exit(2);}
}
static PLI_INT32 setup_case(PLI_BYTE8*){
 family=getenv("K7658_FAMILY");timing=getenv("K7658_TIMING");mode=getenv("K7658_MODE");if(!family||!timing||!mode)exit(2);
 auto args=vpi_iterate(vpiArgument,vpi_handle(vpiSysTfCall,0));foreign_object=vpi_scan(args);if(!foreign_object)exit(2);vpi_free_object(args);
 known_object=vpi_handle_by_name("probe.keep",0);known_callback=watch(known_object,&known_user);if(observing() && !admit(known_callback,&known_user,known_object))exit(2);
 if(!strcmp(timing,"early"))install();observe();return 0;
}
static PLI_INT32 late(PLI_BYTE8*){if(!foreign_present)install();observe();return 0;}
static PLI_INT32 inspect(PLI_BYTE8*){
 if(extra){vvp_vector4_t replacement;extra->filter_vec4(vvp_vector4_t(1,++drive%2?BIT4_1:BIT4_0),replacement,0,1);s_vpi_value value={};value.format=vpiScalarVal;extra->get_value(&value);printf("PRIVATE_VALUE %d\n",value.value.scalar);}
 observe();return 0;
}
static PLI_INT32 cancel(PLI_BYTE8*){if(extra){delete extra;extra=0;foreign_present=false;}else if(!vpi_remove_cb(foreign_callback))exit(2);observe();return 0;}
static PLI_INT32 retired(PLI_BYTE8*){foreign_present=false;observe();return 0;}
static void setup(){
 const char*names[]={"$family_setup","$family_late","$family_inspect","$family_cancel","$family_retired"};PLI_INT32(*funcs[])(PLI_BYTE8*)={setup_case,late,inspect,cancel,retired};
 for(int i=0;i<5;i++){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname=(char*)names[i];t.calltf=funcs[i];vpi_register_systf(&t);}
}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
