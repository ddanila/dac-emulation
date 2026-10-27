/* Initialization-only diagnostic; no coroutine execution or transient claim. */
static void signal_handle_board_budget(struct ng_vvp*ctx)
{
    unsigned long long(*admit)(void*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_admit");
    int(*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_inventory");
    int(*graph)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_inventory");
    int(*scopes)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_inventory");
    if(!admit||!inventory||!graph||!scopes)exit(2);
    callback_budget_file(ctx,inventory,"handles-unadmitted.txt");
    FILE*f=fopen("handle-bindings.txt","w");if(!f)exit(2);
    for(size_t i=0;i<(size_t)ctx->ins+ctx->outs+ctx->inouts;++i){
        struct ngvp_port*port=ctx->ports+i;
        unsigned long long id=admit(port->handle);
        if(!id||admit(port->handle)!=id)exit(2);
        if(fprintf(f,"SH_BIND %zu %llu %p %p\n",i,id,(void*)port,(void*)port->handle)<0)exit(2);
    }
    if(fclose(f))exit(2);
    callback_budget_file(ctx,inventory,"handles-before.txt");
    callback_budget_file(ctx,graph,"handle-graph.txt");
    callback_budget_file(ctx,scopes,"handle-scopes.txt");
    f=fopen("/dev/null","w");if(!f)exit(2);double total=0,minimum=1e99,maximum=0;
    for(unsigned i=0;i<64;++i){
        double start=callback_budget_now();if(inventory(f)||fflush(f))exit(2);
        double elapsed=callback_budget_now()-start;total+=elapsed;
        if(elapsed<minimum)minimum=elapsed;if(elapsed>maximum)maximum=elapsed;
    }
    if(fclose(f))exit(2);
    callback_budget_file(ctx,inventory,"handles-after.txt");
    f=fopen("handle-budget.txt","w");if(!f)exit(2);
    if(fprintf(f,"SH_BUDGET 64 %.9f %.9f %.9f\nSH_DONE\n",total,minimum,maximum)<0||fclose(f))exit(2);
}
