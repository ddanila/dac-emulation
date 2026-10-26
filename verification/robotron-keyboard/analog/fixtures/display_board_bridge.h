/* SPICE owns the coroutine mutex at these boundaries. Typed APIs are resolved
 * from the actual loaded module; supplied opaque handles are never unpacked. */
typedef unsigned long long (*display_lookup_fn)(const void*, int32_t(*)(struct t_cb_data*), char*);
typedef int (*display_null_fn)(const void*, int32_t(*)(struct t_cb_data*), char*);
struct display_board_api {
    int (*family)(FILE*, char*, int32_t(*)(struct t_cb_data*));
    int (*payload)(FILE*);
    int (*association)(FILE*, display_lookup_fn);
    int (*mutate)(display_null_fn);
    display_lookup_fn lookup;
    display_null_fn toggle;
};
static struct display_board_api display_api(struct ng_vvp *ctx)
{
    struct display_board_api api;
    const char *path = getenv("ROBOTRON_DISPLAY_MODULE");
    void *module = path && path[0] == '/' ? dlopen(path, RTLD_LAZY | RTLD_NOLOAD) : NULL;
    if (!module || ctx != robotron_identity_context || !robotron_stop_function) {
        fprintf(stderr, "Missing loaded display module or stop identity\n"); exit(2);
    }
    api.family = dlsym(ctx->vvp_handle, "robotron_vvp_sync_family_inventory");
    api.lookup = dlsym(ctx->vvp_handle, "robotron_vvp_sync_payload_identity");
    api.toggle = dlsym(ctx->vvp_handle, "robotron_vvp_sync_toggle_payload_null");
    api.payload = dlsym(module, "robotron_display_inventory");
    api.association = dlsym(module, "robotron_display_associations");
    api.mutate = dlsym(module, "robotron_display_toggle_callback_data");
    dlclose(module); /* The simulator retains ownership of its loaded module. */
    if (!api.family || !api.lookup || !api.toggle || !api.payload || !api.association || !api.mutate) {
        fprintf(stderr, "Missing typed display board API\n"); exit(2);
    }
    return api;
}
static char *display_snapshot(struct ng_vvp *ctx, struct display_board_api api)
{
    char *text = NULL; size_t length = 0;
    FILE *f = open_memstream(&text, &length);
    if (!f) exit(2);
    int failed = fprintf(f, "VA_BEGIN\n") < 0 ||
        api.family(f, (char*)ctx, robotron_stop_function) || api.payload(f) ||
        api.association(f, api.lookup) || fprintf(f, "VA_END\n") < 0;
    if (fclose(f)) failed = 1;
    if (failed) {free(text); return NULL;}
    return text;
}
static char *display_payload_text(struct display_board_api api)
{
    char *text = NULL; size_t length = 0;
    FILE *f = open_memstream(&text, &length);
    if (!f) exit(2);
    int failed = api.payload(f);
    if (fclose(f)) failed = 1;
    if (failed) {free(text); return NULL;}
    return text;
}
static void private_sync_boundary(struct co_info *info, const char *phase)
{
    const char *mode = getenv("ROBOTRON_PRIVATE_DISPLAY");
    if (!mode || !strcmp(mode, "off")) return;
    if (strcmp(mode, "observe") && strcmp(mode, "corrupt")) {
        fprintf(stderr, "Invalid display board mode\n"); exit(2);
    }
    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;
    struct display_board_api api = display_api(ctx);
    static unsigned long long ordinal;
    char *before = display_snapshot(ctx, api);
    if (!before) {fprintf(stderr, "Invalid display association\n"); exit(2);}
    fprintf(stderr, "VB_BRIDGE %llu %s %.17g\nVB_STAGE before\n%s", ordinal++, phase, info->vtime, before);
    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {
        char *payload_before = display_payload_text(api);
        if (!payload_before) exit(2);
        int changed = api.mutate(api.toggle);
        if (changed != 0 && changed != 1) exit(2);
        if (changed) {
            char *after = display_snapshot(ctx, api);
            char *payload_after = display_payload_text(api);
            /* Restore before any possible transfer back to the HDL scheduler. */
            if (api.mutate(api.toggle) != 1) exit(3);
            char *restored = display_snapshot(ctx, api);
            int rejected = after == NULL;
            int unchanged = payload_after && !strcmp(payload_before, payload_after);
            int equal = restored && !strcmp(before, restored);
            if (restored) fprintf(stderr, "VB_STAGE restored\n%s", restored);
            fprintf(stderr, "VB_FAULT payload_unchanged=%d rejected=%d restored=%d\n", unchanged, rejected, equal);
            free(before); free(after); free(restored); free(payload_before); free(payload_after);
            exit(rejected && unchanged && equal ? 2 : 3);
        }
        free(payload_before);
    }
    char *repeat = display_snapshot(ctx, api);
    if (!repeat) exit(2);
    int equal = !strcmp(before, repeat);
    fprintf(stderr, "VB_STAGE repeat\n%sVB_STABLE equal=%d\n", repeat, equal);
    free(before); free(repeat);
    if (!equal) exit(2);
}
