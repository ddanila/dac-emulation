/* The startup callback is removed from its pending list before the first
 * coroutine yield. Its runtime lifetime remains live until start_cb returns. */
typedef unsigned long long (*startup_lookup_fn)(const void*,int32_t(*)(struct t_cb_data*),char*);
typedef int (*startup_toggle_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,int);
static struct ng_vvp *robotron_start_context;
static struct __vpiHandle *robotron_start_callback;
static int32_t (*robotron_start_function)(struct t_cb_data*);
static unsigned long long robotron_start_lifetime;
static int robotron_start_phase;
static startup_lookup_fn robotron_start_lookup;
static startup_toggle_fn robotron_start_toggle;

void Robotron_start_registration(struct ng_vvp *ctx,struct __vpiHandle *callback,
                                 int32_t (*function)(struct t_cb_data*))
{
    if (!ctx || !callback || !function || robotron_start_context) exit(2);
    robotron_start_lookup=dlsym(ctx->vvp_handle,"robotron_vvp_start_identity");
    robotron_start_toggle=dlsym(ctx->vvp_handle,"robotron_vvp_start_toggle");
    if (!robotron_start_lookup || !robotron_start_toggle) exit(2);
    robotron_start_lifetime=robotron_start_lookup(callback,function,(char*)ctx);
    if (!robotron_start_lifetime) exit(2);
    robotron_start_context=ctx;robotron_start_callback=callback;robotron_start_function=function;
}

void Robotron_start_phase(struct ng_vvp *ctx,int phase)
{
    if (ctx!=robotron_start_context || phase!=robotron_start_phase+1 || phase>2) exit(2);
    robotron_start_phase=phase;
}

static int robotron_start_inventory(FILE *f,struct ng_vvp *ctx)
{
    if (ctx!=robotron_start_context || !robotron_start_lookup ||
        (robotron_start_phase!=1 && robotron_start_phase!=2)) return -1;
    unsigned long long id=robotron_start_lookup(robotron_start_callback,robotron_start_function,(char*)ctx);
    /* Phase 2 is observed only after return to the scheduler and destruction.
     * Never dereference the saved opaque callback after its lifetime ends. */
    if (id!=(robotron_start_phase==1 ? robotron_start_lifetime : 0)) return -1;
    return fprintf(f,"VS_START %d %llu %llu\n",robotron_start_phase,robotron_start_lifetime,id)<0 ? -1 : 0;
}

static int robotron_start_fault(int field)
{
    if (robotron_start_phase!=1 || !robotron_start_toggle) return -1;
    return robotron_start_toggle(robotron_start_callback,robotron_start_function,(char*)robotron_start_context,field);
}
