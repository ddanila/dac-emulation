/* watch() runs before pp metadata is initialized: record opaque identities
 * here, and read port fields only in the paused, initialized inventory. */
typedef unsigned long long (*output_lookup_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,struct __vpiHandle*);
typedef int (*output_toggle_fn)(const void*,int32_t(*)(struct t_cb_data*),char*,struct __vpiHandle*,int);
struct robotron_output_identity {
    struct ngvp_port *port;
    struct __vpiHandle *callback, *signal;
    int32_t (*function)(struct t_cb_data*);
    unsigned long long lifetime;
};
static struct robotron_output_identity *robotron_outputs;
static size_t robotron_outputs_count,robotron_outputs_capacity;
static output_lookup_fn robotron_output_lookup;
static output_toggle_fn robotron_output_toggle;

void Robotron_output_registration(void *port,struct __vpiHandle *callback,
                                  int32_t (*function)(struct t_cb_data*),struct __vpiHandle *signal)
{
    struct ng_vvp *ctx=robotron_identity_context;
    if (!ctx || !ctx->ports || !port || !callback || !function || !signal) exit(2);
    size_t count=(size_t)ctx->outs+ctx->inouts;
    if (!robotron_outputs) {
        if (!count || count>SIZE_MAX/sizeof(*robotron_outputs)) exit(2);
        robotron_outputs=calloc(count,sizeof(*robotron_outputs));
        if (!robotron_outputs) exit(2);
        robotron_outputs_capacity=count;
        robotron_output_lookup=dlsym(ctx->vvp_handle,"robotron_vvp_value_identity");
        robotron_output_toggle=dlsym(ctx->vvp_handle,"robotron_vvp_value_toggle");
        if (!robotron_output_lookup || !robotron_output_toggle) exit(2);
    }
    if (count!=robotron_outputs_capacity || robotron_outputs_count>=count) exit(2);
    size_t index=0;
    while (index<count && port!=(void*)(ctx->ports+ctx->ins+index)) ++index;
    if (index==count || robotron_outputs[index].port) exit(2);
    for (size_t i=0;i<count;i++)
        if (robotron_outputs[i].callback==callback) exit(2);
    unsigned long long id=robotron_output_lookup(callback,function,port,signal);
    if (!id) exit(2);
    robotron_outputs[index]=(struct robotron_output_identity){port,callback,signal,function,id};
    ++robotron_outputs_count;
}

static int robotron_output_inventory(FILE *f,struct ng_vvp *ctx)
{
    if (ctx!=robotron_ports_context || !robotron_outputs || !robotron_output_lookup ||
        robotron_outputs_count!=(size_t)ctx->outs+ctx->inouts) return -1;
    if (fprintf(f,"VW_BEGIN 1 %zu\n",robotron_outputs_count)<0) return -1;
    for (size_t i=0;i<robotron_outputs_count;i++) {
        const struct robotron_output_identity *r=robotron_outputs+i;
        struct ngvp_port *port=ctx->ports+ctx->ins+i;
        if (r->port!=port || port->handle!=r->signal || port->ctx!=ctx ||
            robotron_output_lookup(r->callback,r->function,(char*)port,r->signal)!=r->lifetime) return -1;
        if (fprintf(f,"VW_LINK %zu %llu\n",(size_t)ctx->ins+i,r->lifetime)<0) return -1;
    }
    return fprintf(f,"VW_END\n")<0 || ferror(f) ? -1 : 0;
}

static int robotron_output_fault(int field)
{
    if (!robotron_outputs_count || !robotron_output_toggle) return -1;
    const struct robotron_output_identity *r=robotron_outputs;
    return robotron_output_toggle(r->callback,r->function,(char*)r->port,r->signal,field);
}
