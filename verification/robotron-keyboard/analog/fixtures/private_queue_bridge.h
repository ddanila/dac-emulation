/* Single-Icarus pthread bridge observation. Called only while SPICE owns the
 * coroutine mutex, before releasing it and after reacquiring it in step(). */
static char *private_queue_snapshot(struct ng_vvp *ctx)
{
    int (*observe)(FILE*) = dlsym(ctx->vvp_handle, "robotron_vvp_queue_inventory");
    char *text = NULL;
    size_t length = 0;
    FILE *stream = open_memstream(&text, &length);
    if (!observe || !stream || observe(stream) || fclose(stream)) {
        fprintf(stderr, "Private queue snapshot failed\n"); exit(2);
    }
    return text;
}

static void private_queue_boundary(struct co_info *info, const char *phase)
{
    const char *mode = getenv("ROBOTRON_PRIVATE_QUEUE");
    if (!mode || !strcmp(mode, "off")) return;
    if (strcmp(mode, "observe") && strcmp(mode, "corrupt")) {
        fprintf(stderr, "Invalid private queue mode\n"); exit(2);
    }
    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;
    static unsigned long long ordinal;
    char *before = private_queue_snapshot(ctx);
    fprintf(stderr, "VQ_BRIDGE %llu %s %.17g\nVQ_STAGE before\n%s", ordinal++, phase, info->vtime, before);
    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {
        int (*adjust)(int) = dlsym(ctx->vvp_handle, "robotron_vvp_queue_adjust_first_future");
        if (!adjust) {fprintf(stderr, "Missing private fault API\n"); exit(2);}
        int changed = adjust(1);
        if (changed < 0) {fprintf(stderr, "Private fault API failed\n"); exit(2);}
        if (changed) {
            char *after = private_queue_snapshot(ctx);
            if (adjust(-1) != 1) {fprintf(stderr, "Private fault restoration failed\n"); exit(2);}
            char *restored = private_queue_snapshot(ctx);
            int detected = strcmp(before, after) != 0;
            int equal = strcmp(before, restored) == 0;
            fprintf(stderr, "VQ_STAGE changed\n%sVQ_STAGE restored\n%sVQ_FAULT detected=%d restored=%d\n", after, restored, detected, equal);
            free(before); free(after); free(restored);
            exit(detected && equal ? 2 : 3);
        }
    }
    char *repeat = private_queue_snapshot(ctx);
    int equal = strcmp(before, repeat) == 0;
    fprintf(stderr, "VQ_STAGE repeat\n%sVQ_STABLE equal=%d\n", repeat, equal);
    free(before); free(repeat);
    if (!equal) exit(2);
}
