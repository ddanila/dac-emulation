#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static int(*inventory)(FILE*);static unsigned round_id;
static std::string snapshot(bool refuse=false){
 if(!inventory)return "";char*p=0;size_t n=0;FILE*f=open_memstream(&p,&n);if(!f)exit(2);
 int rc=inventory(f);if(fclose(f))exit(2);std::string s(p,n);free(p);if(refuse?(rc>=0||n):rc!=0)exit(2);return s;
}
static void image(const char*label){if(inventory)printf("IMAGE %s%u\n%sIMAGE_END\n",label,round_id,snapshot().c_str());}
static PLI_INT32 run(PLI_BYTE8*){
 auto p=dynamic_cast<__vpiBinaryConst*>(vpi_handle_by_name("test.P",0));
 auto w=dynamic_cast<__vpiBinaryConst*>(vpi_handle_by_name("test.W",0));
 auto r=dynamic_cast<__vpiRealConst*>(vpi_handle_by_name("test.R",0));
 auto str=vpi_handle_by_name("test.S",0);if(!p||!w||!r||!str||p->bits.size()!=4||w->bits.size()!=80)exit(2);
 const char*mode=getenv("K7658_PORT_PAYLOAD");if(!mode)exit(2);
 if(!strcmp(mode,"on")){inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");if(!inventory)exit(2);}
 ++round_id;printf("ROUND %u\n",round_id);auto before=snapshot();image("before");
 auto bit=p->bits.value(0);p->bits.set_bit(0,BIT4_0);image("small");p->bits.set_bit(0,bit);
 bit=w->bits.value(70);w->bits.set_bit(70,bit==BIT4_0?BIT4_1:BIT4_0);image("wide");w->bits.set_bit(70,bit);
 auto sign=p->signed_flag;p->signed_flag=!sign;image("signed");p->signed_flag=sign;
 auto sized=p->sized_flag;p->sized_flag=!sized;image("sized");p->sized_flag=sized;
 double real=r->value;r->value=2.5;image("real");r->value=real;
 auto bits=p->bits;p->bits.resize(5);snapshot(true);printf("REFUSED width\n");p->bits=bits;
 auto scope=dynamic_cast<__vpiScope*>(vpi_handle(vpiScope,p));if(!scope)exit(2);auto members=scope->intern;
 for(auto i=scope->intern.begin();i!=scope->intern.end();++i)if(*i==p){scope->intern.erase(i);break;}
 snapshot(true);printf("REFUSED missing-owner\n");scope->intern=members;
 scope->intern.push_back(p);snapshot(true);printf("REFUSED duplicate-owner\n");scope->intern=members;
 if(snapshot()!=before||r->value!=1.5||p->bits.value(0)!=BIT4_1)exit(2);
 image("restored");printf("RESTORED %u\n",round_id);return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_payload";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
