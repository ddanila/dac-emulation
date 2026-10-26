#include <libproc.h>
#include <sys/resource.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
int main(int argc,char **argv) {
  for(int i=1;i<argc;i++) {
    char *end; errno=0; long value=strtol(argv[i],&end,10);
    if(errno||*end||value<=0||value>INT_MAX) return 2;
    struct rusage_info_v4 r={0};
    if(proc_pid_rusage((int)value,RUSAGE_INFO_V4,(rusage_info_t *)&r)) {
      printf("{\"pid\":%ld,\"errno\":%d}\n",value,errno);continue;
    }
    printf("{\"pid\":%ld,\"startAbsoluteTime\":%" PRIu64 ",\"exitAbsoluteTime\":%" PRIu64 ",\"residentBytes\":%" PRIu64 ",\"footprintBytes\":%" PRIu64 ",\"lifetimeMaximumFootprintBytes\":%" PRIu64 "}\n",value,r.ri_proc_start_abstime,r.ri_proc_exit_abstime,r.ri_resident_size,r.ri_phys_footprint,r.ri_lifetime_max_phys_footprint);
  }
  return 0;
}
