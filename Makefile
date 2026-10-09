CC ?= cc
AR ?= ar
CFLAGS ?= -O2 -g
CPPFLAGS += -Imachines/juku -Ithird_party/cpu/i8080 -Icommon/media -Icommon/trace
WARN = -std=c11 -Wall -Wextra -Werror
CORE = machines/juku/juku.c machines/juku/juk_disk.c machines/juku/juku_fdc.c \
       third_party/cpu/i8080/i8080.c common/media/media.c common/trace/trace.c
HOST = runners/native/juku_trace.c runners/native/juku_disk_file.c
OBJECTS = $(CORE:%.c=build/%.o)

.PHONY: all test clean
all: build/libdac-juku.a build/juku-trace

build/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) -MMD -MP -c $< -o $@

build/libdac-juku.a: $(OBJECTS)
	$(AR) rcs $@ $^

build/juku-trace: $(HOST:%.c=build/%.o) build/libdac-juku.a
	$(CC) $(CFLAGS) $^ -o $@

build/support-test: tests/integration/support_test.c build/libdac-juku.a
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $< build/libdac-juku.a -o $@

test: all build/support-test
	./build/support-test

clean:
	rm -rf build

-include $(OBJECTS:.o=.d) $(HOST:%.c=build/%.d)
