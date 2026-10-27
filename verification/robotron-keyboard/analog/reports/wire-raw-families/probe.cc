#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <string>
#include <vpi_user.h>
#include "vvp_net.h"
#include "vvp_net_sig.h"
#include "schedule.h"
class ExtraWire4: public vvp_wire_vec4 {
 bool invert_;
 public:
 ExtraWire4():vvp_wire_vec4(1,BIT4_X),invert_(true){}
 prop_t filter_vec4(const vvp_vector4_t& value,vvp_vector4_t& rep,unsigned base,unsigned width) override {
  auto altered=value;if(invert_)altered.set_bit(0,~altered.value(0));
  return vvp_wire_vec4::filter_vec4(altered,rep,base,width);
 }
};
class ExtraWire8: public vvp_wire_vec8 {
 bool invert_;
 public:
 ExtraWire8():vvp_wire_vec8(1),invert_(true){}
 prop_t filter_vec8(const vvp_vector8_t& value,vvp_vector8_t& rep,unsigned base,unsigned width) override {
  auto altered=value;if(invert_)altered.set_bit(0,vvp_scalar_t(~altered.value(0).value(),3,5));
  return vvp_wire_vec8::filter_vec8(altered,rep,base,width);
 }
};
static vvp_net_t* admitted;static vvp_net_t* foreign;
static const char* family;static const char* phase;static bool enabled;
static void allocate(){
 foreign=new vvp_net_t;
 if(!strcmp(family,"derived4"))foreign->fil=new ExtraWire4;
 else if(!strcmp(family,"derived8"))foreign->fil=new ExtraWire8;
 else if(!strcmp(family,"real"))foreign->fil=new vvp_wire_real;
 else exit(3);
}
static void observe(unsigned stage){
 if(!enabled)return;
 auto api=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_wire_raw_inventory"));
 auto types=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_net_types"));
 if(!api || !types)exit(3);
 char* data=0;size_t size=0;FILE* out=open_memstream(&data,&size);if(!out)exit(3);
 int result=api(out);if(fclose(out))exit(3);
 if(foreign){
  if(result!=-1 || size){if(size)fwrite(data,1,size,stdout);exit(3);}
  printf("RAW_REFUSED %u\n",stage);
 }else{
  if(result || !size)exit(3);
  printf("RAW_ADMITTED %u\n%s",stage,data);
 }
 free(data);
 std::string name=std::string(family)+"-"+phase+"-"+std::to_string(stage)+".types";
 out=fopen(name.c_str(),"w");if(!out || types(out) || fclose(out))exit(3);
}
static PLI_INT32 startup(p_cb_data){
 family=getenv("K7658_RAW_FAMILY");phase=getenv("K7658_RAW_PHASE");
 const char* mode=getenv("K7658_RAW_MODE");if(!family || !phase || !mode)exit(3);enabled=!strcmp(mode,"observe");
 admitted=new vvp_net_t;admitted->fil=new vvp_wire_vec8(1);
 auto ordinary=new vvp_net_t;ordinary->fil=new vvp_wire_vec4(1,BIT4_X);
 if(!strcmp(phase,"early"))allocate();
 printf("RAW_FAMILY %s %s\n",family,phase);observe(0);return 0;
}
static unsigned step;
static PLI_INT32 drive(PLI_BYTE8*){
 ++step;if(!foreign)allocate();observe(step);
 const auto bit=step==1?BIT4_0:BIT4_1;
 vvp_vector8_t bits(1);bits.set_bit(0,vvp_scalar_t(bit,3,5));vvp_vector8_t rep;
 auto wire=static_cast<vvp_wire_vec8*>(admitted->fil);wire->filter_vec8(bits,rep,0,1);
 printf("RAW_VALUE %u admitted %u\n",step,unsigned(wire->value(0)));
 if(!strcmp(family,"derived4")){
  vvp_vector4_t rep4;foreign->fil->filter_vec4(vvp_vector4_t(1,bit),rep4,0,1);
  printf("RAW_VALUE %u foreign %u\n",step,unsigned(static_cast<ExtraWire4*>(foreign->fil)->value(0)));
 }else if(!strcmp(family,"derived8")){
  foreign->fil->filter_vec8(bits,rep,0,1);
  printf("RAW_VALUE %u foreign %u\n",step,unsigned(static_cast<ExtraWire8*>(foreign->fil)->value(0)));
 }else{
  double v=step==1?1.25:-2.5;foreign->fil->filter_real(v);
  printf("RAW_REAL %u %.2f\n",step,static_cast<vvp_wire_real*>(foreign->fil)->real_value());
 }
 observe(step+2);return 0;
}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(3);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$raw_family_drive";task.calltf=drive;vpi_register_systf(&task);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
