#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <string>
#include <vpi_user.h>
#include "logic.h"
class ExtraAnd: public vvp_fun_and {
 bool invert_input;
 public:
 ExtraAnd():vvp_fun_and(1,false),invert_input(true){}
 void recv_vec4(vvp_net_ptr_t p,const vvp_vector4_t& bits,vvp_context_t ctx) override {
  vvp_vector4_t value(bits);if(p.port()==0 && invert_input)value.set_bit(0,~value.value(0));
  vvp_fun_and::recv_vec4(p,value,ctx);
 }
};
class ExtraBuf: public vvp_fun_buf {
 bool invert_input;
 public:
 ExtraBuf():vvp_fun_buf(1),invert_input(true){}
 void recv_vec4(vvp_net_ptr_t p,const vvp_vector4_t& bits,vvp_context_t ctx) override {
  vvp_vector4_t value(bits);if(invert_input)value.set_bit(0,~value.value(0));
  vvp_fun_buf::recv_vec4(p,value,ctx);
 }
};
class Sink: public vvp_net_fun_t {
 unsigned index;
 public:
 explicit Sink(unsigned i):index(i){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& bits,vvp_context_t) override {
  printf("FAMILY_VALUE %llu %u %u\n",(unsigned long long)schedule_simtime(),index,unsigned(bits.value(0)));
 }
};
static vvp_net_t* nodes[2];
static PLI_INT32 startup(p_cb_data) {
 const char *family=getenv("K7658_GATE_FAMILY");if(!family)exit(2);
 for(unsigned i=0;i<2;i++){
  if(i==1 && !strcmp(getenv("K7658_GATE_MODE"),"observe")){
   auto reference=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_gate_reference"));
   std::string name=std::string(family)+".reference";FILE *out=fopen(name.c_str(),"w");
   if(!reference || !out || reference(out) || fclose(out))exit(3);
  }
  nodes[i]=new vvp_net_t;
  if(!i)nodes[i]->fun=new vvp_fun_and(1,false);
  else if(!strcmp(family,"equiv"))nodes[i]->fun=new vvp_fun_equiv;
  else if(!strcmp(family,"impl"))nodes[i]->fun=new vvp_fun_impl;
  else if(!strcmp(family,"derived-boolean"))nodes[i]->fun=new ExtraAnd;
  else if(!strcmp(family,"derived-unary"))nodes[i]->fun=new ExtraBuf;
  else exit(2);
  auto sink=new vvp_net_t;sink->fun=new Sink(i);nodes[i]->link(vvp_net_ptr_t(sink,0));
 }
 printf("FAMILY_PRESENT %s\n",family);
 const char *mode=getenv("K7658_GATE_MODE");
 if(mode && !strcmp(mode,"observe")){
  auto types=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_net_types"));
  auto inventory=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_gate_inventory"));
  if(!types || !inventory)exit(3);
  std::string name=std::string(family)+".types";FILE *out=fopen(name.c_str(),"w");
  if(!out || types(out) || fclose(out))exit(3);
  const char* names[]={"robotron_vvp_gate_inventory","robotron_vvp_gate_reference","robotron_vvp_gate_delta_inventory"};
  for(const char* name:names){
  auto api=reinterpret_cast<int (*)(FILE*)>(dlsym(RTLD_DEFAULT,name));if(!api)exit(3);
  char *data=0;size_t size=0;out=open_memstream(&data,&size);if(!out)exit(3);
  int result=api(out);if(fclose(out))exit(3);
  if(result!=-1 || size){if(size)fwrite(data,1,size,stdout);exit(3);}
  free(data);}
  printf("GATE_REFUSED\n");exit(2);
 }
 return 0;
}
static PLI_INT32 drive(PLI_BYTE8*) {
 const char *family=getenv("K7658_GATE_FAMILY");
 for(unsigned i=0;i<2;i++)for(unsigned port=0;port<((i && !strcmp(family,"derived-unary"))?1:4);port++)
  nodes[i]->fun->recv_vec4(vvp_net_ptr_t(nodes[i],port),vvp_vector4_t(1,port?BIT4_1:BIT4_0),0);
 return 0;
}
static void setup() {
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(3);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$gate_family_drive";task.calltf=drive;vpi_register_systf(&task);
}
extern "C" { void (*vlog_startup_routines[])(void)={setup,0}; }
