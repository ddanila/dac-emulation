#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <string>
#include <vpi_user.h>
#include "schedule.h"
#include "concat.h"
class ExtraConcat4: public vvp_fun_concat {
 bool invert_;
 public:
 ExtraConcat4():vvp_fun_concat(1,0,0,0),invert_(true){}
 void drive(vvp_net_t* n,vvp_bit4_t bit){recv_vec4(vvp_net_ptr_t(n,0),vvp_vector4_t(1,invert_?~bit:bit),0);}
};
class ExtraConcat8: public vvp_fun_concat8 {
 bool invert_;
 public:
 ExtraConcat8():vvp_fun_concat8(1,0,0,0),invert_(true){}
 void drive(vvp_net_t* n,vvp_bit4_t bit){recv_vec4(vvp_net_ptr_t(n,0),vvp_vector4_t(1,invert_?~bit:bit),0);}
};
class Sink: public vvp_net_fun_t {
 const char* label;
 public:
 explicit Sink(const char* s):label(s){}
 void recv_vec4(vvp_net_ptr_t,const vvp_vector4_t& b,vvp_context_t) override {printf("CONCAT_VALUE %llu %s %u\n",(unsigned long long)schedule_simtime(),label,unsigned(b.value(0)));}
 void recv_vec8(vvp_net_ptr_t,const vvp_vector8_t& b) override {printf("CONCAT_VALUE %llu %s %u\n",(unsigned long long)schedule_simtime(),label,unsigned(b.value(0).value()));}
};
static vvp_net_t *admitted,*foreign;
static const char *family,*phase;static bool enabled;
static void connect(vvp_net_t* n,const char* label){auto s=new vvp_net_t;s->fun=new Sink(label);n->link(vvp_net_ptr_t(s,0));}
static void allocate(){
 foreign=new vvp_net_t;
 if(!strcmp(family,"derived4"))foreign->fun=new ExtraConcat4;
 else if(!strcmp(family,"derived8"))foreign->fun=new ExtraConcat8;
 else exit(3);
 connect(foreign,"foreign");
}
static void observe(unsigned stage){
 if(!enabled)return;
 auto api=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_concat_inventory"));
 auto types=reinterpret_cast<int(*)(FILE*)>(dlsym(RTLD_DEFAULT,"robotron_vvp_net_types"));
 if(!api || !types)exit(3);
 char* data=0;size_t size=0;FILE* out=open_memstream(&data,&size);if(!out)exit(3);
 int result=api(out);if(fclose(out))exit(3);
 if(foreign){if(result!=-1 || size){if(size)fwrite(data,1,size,stdout);exit(3);}printf("CONCAT_REFUSED %u\n",stage);}
 else {if(result || !size)exit(3);printf("CONCAT_ADMITTED %u\n%s",stage,data);}
 free(data);
 std::string name=std::string(family)+"-"+phase+"-"+std::to_string(stage)+".types";
 out=fopen(name.c_str(),"w");if(!out || types(out) || fclose(out))exit(3);
}
static PLI_INT32 startup(p_cb_data){
 family=getenv("K7658_CONCAT_FAMILY");phase=getenv("K7658_CONCAT_PHASE");const char* mode=getenv("K7658_CONCAT_MODE");
 if(!family || !phase || !mode)exit(3);enabled=!strcmp(mode,"observe");
 admitted=new vvp_net_t;admitted->fun=new vvp_fun_concat8(1,0,0,0);connect(admitted,"admitted");
 if(!strcmp(phase,"early"))allocate();
 printf("CONCAT_FAMILY %s %s\n",family,phase);observe(0);return 0;
}
static unsigned step;
static PLI_INT32 drive(PLI_BYTE8*){
 ++step;if(!foreign)allocate();observe(step);
 auto bit=step==1?BIT4_0:BIT4_1;
 admitted->fun->recv_vec4(vvp_net_ptr_t(admitted,0),vvp_vector4_t(1,bit),0);
 if(!strcmp(family,"derived4"))static_cast<ExtraConcat4*>(foreign->fun)->drive(foreign,bit);
 else static_cast<ExtraConcat8*>(foreign->fun)->drive(foreign,bit);
 observe(step+2);return 0;
}
static void setup(){
 s_cb_data cb={};cb.reason=cbEndOfCompile;cb.cb_rtn=startup;if(!vpi_register_cb(&cb))exit(3);
 s_vpi_systf_data task={};task.type=vpiSysTask;task.tfname="$concat_family_drive";task.calltf=drive;vpi_register_systf(&task);
}
extern "C" {void(*vlog_startup_routines[])(void)={setup,0};}
