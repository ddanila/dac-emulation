#define _GNU_SOURCE
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <dlfcn.h>
#include "vpi_priv.h"
static unsigned round_id;
static PLI_INT32 run(PLI_BYTE8*){
 const char*mode=getenv("K7658_PORT_PAYLOAD");const char*kind=getenv("ROBOTRON_PARAMETER_CLASS");if(!mode||!kind)exit(2);
 auto p=vpi_handle_by_name("test.P",0);auto w=vpi_handle_by_name("test.W",0);auto r=vpi_handle_by_name("test.R",0);auto s=vpi_handle_by_name("test.S",0);
 if(!p||!w||!r||!s||vpi_get(vpiType,p)!=vpiParameter||vpi_get(vpiType,w)!=vpiParameter||vpi_get(vpiType,r)!=vpiParameter||vpi_get(vpiType,s)!=vpiParameter)exit(2);
 s_vpi_value v={};v.format=vpiIntVal;vpi_get_value(p,&v);int small=v.value.integer;
 v.format=vpiHexStrVal;vpi_get_value(w,&v);std::string wide=v.value.str;
 v.format=vpiRealVal;vpi_get_value(r,&v);double real=v.value.real;
 v.format=vpiStringVal;vpi_get_value(s,&v);int bits=vpi_get(vpiSize,s);
 if(small!=3||wide!="123456789abcdef01234"||real!=1.5||bits!=24||memcmp(v.value.str,"A B",3))exit(2);
 ++round_id;printf("ROUND %u\nVALUES %d %s %.1f %d 412042\n",round_id,small,wide.c_str(),real,bits);
 auto count=(unsigned(*)())dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_unsupported_count");
 if(count){unsigned expected=!strcmp(kind,"binary")?2:strcmp(kind,"none")?1:0;if(count()!=expected)exit(2);printf("CLASS %s %u\n",kind,count());}
 if(!strcmp(mode,"on")){
  auto inventory=(int(*)(FILE*))dlsym(RTLD_DEFAULT,"robotron_vvp_parameter_inventory");if(!inventory||!count)exit(2);
  char*bytes=0;size_t n=0;FILE*f=open_memstream(&bytes,&n);if(!f)exit(2);int rc=inventory(f);if(fclose(f))exit(2);
  if(strcmp(kind,"none")){if(rc>=0||n)exit(2);printf("REFUSED %u %s\n",round_id,kind);}
  else{if(rc||!n)exit(2);printf("IMAGE %u\n%sIMAGE_END\n",round_id,bytes);}
  free(bytes);
 }
 return 0;
}
static void setup(){s_vpi_systf_data t={};t.type=vpiSysTask;t.tfname="$parameter_class";t.calltf=run;vpi_register_systf(&t);}
extern "C"{void(*vlog_startup_routines[])(void)={setup,0};}
