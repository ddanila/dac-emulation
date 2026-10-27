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
