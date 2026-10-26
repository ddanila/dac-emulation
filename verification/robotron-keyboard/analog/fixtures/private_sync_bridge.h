/* Function identity is deliberately unresolved here (NULL expected function).
 * User-data identity is checked against the actual ng_vvp context; its referents
 * are not serialized by this header observer.
 * Single-Icarus pthread bridge observation. Called only while SPICE owns the
 * coroutine mutex, before releasing it and after reacquiring it in step(). */
static char *private_sync_snapshot(struct ng_vvp *ctx)
{
    struct t_cb_data;
    int (*observe)(FILE*, char*, int(*)(struct t_cb_data*)) = dlsym(ctx->vvp_handle, "robotron_vvp_sync_inventory");
    char *text = NULL;
    size_t length = 0;
    FILE *stream = open_memstream(&text, &length);
    if (!observe || !stream || observe(stream, (char*)ctx, NULL) || fclose(stream)) {
        fprintf(stderr, "Private synchronization callback snapshot failed\n"); exit(2);
    }
    return text;
}

static void private_sync_boundary(struct co_info *info, const char *phase)
{
    const char *mode = getenv("ROBOTRON_PRIVATE_SYNC");
    if (!mode || !strcmp(mode, "off")) return;
    if (strcmp(mode, "observe") && strcmp(mode, "corrupt")) {
        fprintf(stderr, "Invalid private queue mode\n"); exit(2);
    }
    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;
    static unsigned long long ordinal;
    char *before = private_sync_snapshot(ctx);
    fprintf(stderr, "VS_BRIDGE %llu %s %.17g\nVS_STAGE before\n%s", ordinal++, phase, info->vtime, before);
    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {
        int (*adjust)(void) = dlsym(ctx->vvp_handle, "robotron_vvp_sync_toggle_queued_mode");
        if (!adjust) {fprintf(stderr, "Missing private fault API\n"); exit(2);}
        int changed = adjust();
        if (changed < 0) {fprintf(stderr, "Private fault API failed\n"); exit(2);}
        if (changed) {
            char *after = private_sync_snapshot(ctx);
            if (adjust() != 1) {fprintf(stderr, "Private fault restoration failed\n"); exit(2);}
            char *restored = private_sync_snapshot(ctx);
            int detected = strcmp(before, after) != 0;
            int equal = strcmp(before, restored) == 0;
            fprintf(stderr, "VS_STAGE changed\n%sVS_STAGE restored\n%sVS_FAULT detected=%d restored=%d\n", after, restored, detected, equal);
            free(before); free(after); free(restored);
            exit(detected && equal ? 2 : 3);
        }
    }
    char *repeat = private_sync_snapshot(ctx);
    int equal = strcmp(before, repeat) == 0;
    fprintf(stderr, "VS_STAGE repeat\n%sVS_STABLE equal=%d\n", repeat, equal);
    free(before); free(repeat);
    if (!equal) exit(2);
}
