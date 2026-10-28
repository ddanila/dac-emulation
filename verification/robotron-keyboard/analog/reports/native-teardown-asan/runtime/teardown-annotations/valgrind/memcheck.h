/* Teardown-only compatibility header, NOT a Valgrind implementation.
 * Native CHECK_WITH_VALGRIND cleanup is enabled. Allocation annotations are
 * explicitly disabled; AddressSanitizer instruments real allocations instead.
 */
#ifndef ROBOTRON_TEARDOWN_ANNOTATIONS_H
#define ROBOTRON_TEARDOWN_ANNOTATIONS_H
#include <stdio.h>
#define RUNNING_ON_VALGRIND 0
#define VALGRIND_MAKE_MEM_NOACCESS(a,b) do { (void)(a); (void)(b); } while(0)
#define VALGRIND_CREATE_MEMPOOL(a,b,c) do { (void)(a); (void)(b); (void)(c); } while(0)
#define VALGRIND_MEMPOOL_ALLOC(a,b,c) do { (void)(a); (void)(b); (void)(c); } while(0)
#define VALGRIND_MEMPOOL_FREE(a,b) do { (void)(a); (void)(b); } while(0)
#define VALGRIND_DESTROY_MEMPOOL(a) do { (void)(a); } while(0)
#define VALGRIND_PRINTF(...) fprintf(stderr,__VA_ARGS__)
#endif
