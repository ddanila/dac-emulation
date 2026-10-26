/* Registered on the HDL thread after all ports and output values are seeded,
 * before its first yield. Input-only `new` is intentionally never inspected. */
struct robotron_port_identity {
    struct __vpiHandle *handle;
    uint16_t bits;
    uint32_t position;
    char *name;
};
static struct ng_vvp *robotron_ports_context;
static struct ngvp_port *robotron_ports_base;
static struct co_info *robotron_ports_cosim;
static void *robotron_ports_library;
static uint32_t robotron_ports_ins, robotron_ports_outs, robotron_ports_inouts;
static size_t robotron_ports_count;
static struct robotron_port_identity *robotron_ports_ids;

void Robotron_ports_identity(struct ng_vvp *ctx,
                            char *(*name)(int32_t, struct __vpiHandle*), int32_t property)
{
    if (!ctx || ctx != robotron_identity_context || !name || robotron_ports_context ||
        !ctx->ports || !ctx->cosim_context || !ctx->vvp_handle) {
        fprintf(stderr,"Invalid port identity handoff\n"); exit(2);
    }
    uint64_t count = (uint64_t)ctx->ins + ctx->outs + ctx->inouts;
    if (!count || count > SIZE_MAX / sizeof(*robotron_ports_ids)) exit(2);
    robotron_ports_ids = calloc((size_t)count, sizeof(*robotron_ports_ids));
    if (!robotron_ports_ids) exit(2);
    uint64_t position = 0;
    for (size_t i=0; i<count; ++i) {
        struct ngvp_port *p=ctx->ports+i;
        if (i==0 || i==ctx->ins || i==(uint64_t)ctx->ins+ctx->outs) position=0;
        if (!p->handle || p->ctx!=ctx || !p->bits || p->bits>32 || p->position!=position) exit(2);
        position += p->bits;
        const char *text=name(property,p->handle);
        if (!text || !*text) exit(2);
        for (size_t j=0; j<i; ++j)
            if (robotron_ports_ids[j].handle==p->handle || !strcmp(robotron_ports_ids[j].name,text)) exit(2);
        robotron_ports_ids[i].handle=p->handle;
        robotron_ports_ids[i].bits=p->bits;
        robotron_ports_ids[i].position=p->position;
        robotron_ports_ids[i].name=strdup(text);
        if (!robotron_ports_ids[i].name) exit(2);
    }
    robotron_ports_context=ctx; robotron_ports_base=ctx->ports;
    robotron_ports_cosim=ctx->cosim_context; robotron_ports_library=ctx->vvp_handle;
    robotron_ports_ins=ctx->ins; robotron_ports_outs=ctx->outs; robotron_ports_inouts=ctx->inouts;
    robotron_ports_count=(size_t)count;
}

static int robotron_ports_inventory(FILE *f, struct ng_vvp *ctx)
{
    if (!f || !ctx || ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base ||
        ctx->cosim_context!=robotron_ports_cosim || ctx->vvp_handle!=robotron_ports_library ||
        ctx->ins!=robotron_ports_ins || ctx->outs!=robotron_ports_outs || ctx->inouts!=robotron_ports_inouts) return -1;
    uint32_t inputs=0,outputs=0;
    /* Check identities before any handle use or observation of port values. */
    for (size_t i=0; i<robotron_ports_count; ++i) {
        const struct ngvp_port *p=ctx->ports+i;
        const struct robotron_port_identity *id=robotron_ports_ids+i;
        unsigned allowed=i<ctx->ins ? IN_PENDING : (i<(uint64_t)ctx->ins+ctx->outs ? OUT_PENDING : IN_PENDING|OUT_PENDING);
        if (p->handle!=id->handle || p->ctx!=ctx || p->bits!=id->bits || p->position!=id->position || (p->flags & ~allowed)) return -1;
        inputs += !!(p->flags & IN_PENDING); outputs += !!(p->flags & OUT_PENDING);
    }
    if (inputs!=ctx->in_pending || outputs!=ctx->out_pending || (ctx->stop!=0 && ctx->stop!=1)) return -1;
    if (fprintf(f,"VP_BEGIN 1 %u %u %u\nVP_CONTEXT %a %a %u %u %d\n",ctx->ins,ctx->outs,ctx->inouts,
                ctx->base_time,ctx->tick_length,ctx->in_pending,ctx->out_pending,ctx->stop)<0) return -1;
    for (size_t i=0; i<robotron_ports_count; ++i) {
        const struct ngvp_port *p=ctx->ports+i;
        unsigned direction=i<ctx->ins ? 1 : (i<(uint64_t)ctx->ins+ctx->outs ? 2 : 3);
        if (fprintf(f,"VP_PORT %zu %u %u %u %u %d %d ",i,direction,p->bits,p->position,p->flags,p->previous.aval,p->previous.bval)<0) return -1;
        if (direction==1) {
            if (fprintf(f,"- - ")<0) return -1;
        } else if (fprintf(f,"%d %d ",p->new.aval,p->new.bval)<0) return -1;
        for (const unsigned char *s=(const unsigned char*)robotron_ports_ids[i].name; *s; ++s)
            if (fprintf(f,"%02x",*s)<0) return -1;
        if (fprintf(f,"\n")<0) return -1;
    }
    return fprintf(f,"VP_END\n")<0 || ferror(f) ? -1 : 0;
}
