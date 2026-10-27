/* Diagnostic-only: called after the real bridge's port initialization and
 * output seeding, before its first coroutine advance. It terminates the run. */
#include <time.h>
static double callback_budget_now(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(2);return t.tv_sec+t.tv_nsec*1e-9;}
static void callback_budget_file(struct ng_vvp*ctx,int(*api)(FILE*),const char*name)
{(void)ctx;FILE*f=fopen(name,"w");if(!f||api(f)||fclose(f))exit(2);}
void Robotron_callback_budget(struct ng_vvp*ctx)
{
    if(ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base ||
       robotron_outputs_count!=(size_t)ctx->outs+ctx->inouts)exit(2);
    int(*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_inventory");
    output_lookup_fn admit=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_admit");
    if(!inventory||!admit)exit(2);
    FILE*f=fopen("ports.txt","w");if(!f||robotron_ports_inventory(f,ctx)||fclose(f))exit(2);
    f=fopen("outputs.txt","w");if(!f||robotron_output_inventory(f,ctx)||fclose(f))exit(2);
    char*text=NULL;size_t size=0;f=open_memstream(&text,&size);if(!f)exit(2);
    int status=inventory(f);if(fclose(f)||status!=-1||size)exit(2);free(text);
    f=fopen("bindings.txt","w");if(!f)exit(2);
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        if(admit(r->callback,r->function,(char*)r->port,r->signal)!=r->lifetime)exit(2);
        if(fprintf(f,"CB_BIND %zu %llu %p %p %p %p\n",(size_t)ctx->ins+i,r->lifetime,(void*)r->port,(void*)r->callback,(void*)r->signal,(void*)r->function)<0)exit(2);
    }
    if(fclose(f))exit(2);
    callback_budget_file(ctx,inventory,"callbacks-before.txt");
    f=fopen("/dev/null","w");if(!f)exit(2);
    double sum=0,minimum=1e99,maximum=0;
    for(int i=0;i<64;i++){
        double start=callback_budget_now();if(inventory(f)||fflush(f))exit(2);
        double elapsed=callback_budget_now()-start;sum+=elapsed;
        if(elapsed<minimum)minimum=elapsed;if(elapsed>maximum)maximum=elapsed;
    }
    if(fclose(f))exit(2);
    callback_budget_file(ctx,inventory,"callbacks-after.txt");
    f=fopen("budget.txt","w");if(!f)exit(2);
    fprintf(f,"CB_BUDGET 64 %.9f %.9f %.9f\nCB_UNADMITTED_REFUSED\nCB_BUDGET_DONE\n",sum,minimum,maximum);
    if(fclose(f))exit(2);
    /* This diagnostic deliberately does not execute the transient campaign. */
    exit(0);
}
