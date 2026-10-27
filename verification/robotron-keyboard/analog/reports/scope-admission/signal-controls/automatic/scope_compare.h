/* Compare both complete native implementations before returning any output. */
static int scope_compare(FILE*out,const char*name,const char*reference,const char*label)
{
 auto current=(int(*)(FILE*))dlsym(RTLD_DEFAULT,name);
 auto previous=(int(*)(FILE*))dlsym(RTLD_DEFAULT,reference);if(!current||!previous)exit(2);
 char*a=0,*b=0;size_t na=0,nb=0;FILE*fa=open_memstream(&a,&na),*fb=open_memstream(&b,&nb);if(!fa||!fb)exit(2);
 int ra=current(fa),rb=previous(fb);if(fclose(fa)||fclose(fb)||ra!=rb||na!=nb||memcmp(a,b,na))exit(2);
 if(ra && na)exit(2);
 printf("SCOPE_EQ %s %d %zu\n",label,ra,na);
 if(!ra && fwrite(a,1,na,out)!=na)exit(2);free(a);free(b);return ra;
}
static int scope_compare_signals(FILE*f){return scope_compare(f,"robotron_vvp_signal_handle_inventory","robotron_vvp_signal_handle_reference_inventory","signals");}
static int scope_compare_links(FILE*f){return scope_compare(f,"robotron_vvp_callback_signal_inventory","robotron_vvp_callback_signal_reference_inventory","links");}
static void*scope_checked_dlsym(void*handle,const char*name)
{
 if(!strcmp(name,"robotron_vvp_signal_handle_inventory"))return (void*)scope_compare_signals;
 if(!strcmp(name,"robotron_vvp_callback_signal_inventory"))return (void*)scope_compare_links;
 return dlsym(handle,name);
}
#define dlsym scope_checked_dlsym
