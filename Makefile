ROBOTRON_OBJECTS = build/machines/robotron1715m/disk.o build/machines/robotron1715m/robotron.o build/machines/robotron1715m/keyboard.o build/machines/robotron1715m/sio.o
CC ?= cc
AR ?= ar
NODE ?= node
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

test: all build/support-test build/machines-test
	./build/support-test
	./build/machines-test

clean:
	rm -rf build

-include $(OBJECTS:.o=.d) $(HOST:%.c=build/%.d)

Z80_OBJECTS = build/common/cpu/z80.o build/machines/vjuga/vjuga.o
all: build/vjuga-boot
build/vjuga-boot: build/runners/native/vjuga_boot.o $(Z80_OBJECTS)
	$(CC) $(CFLAGS) $^ -o $@
-include $(Z80_OBJECTS:.o=.d) build/runners/native/vjuga_boot.d

all: build/robotron-boot
build/robotron-boot: build/runners/native/robotron_boot.o $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CFLAGS) $^ -o $@
-include build/runners/native/robotron_boot.d build/machines/robotron1715m/robotron.d

build/machines-test: tests/integration/machines_test.c $(ROBOTRON_OBJECTS) $(Z80_OBJECTS) build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

build/browser-reference: tests/integration/wasm_reference.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

.PHONY: wasm test-wasm
wasm:
	bash runners/browser/build.sh
	python3 tools/build_demo.py

test-wasm: wasm
	"$(NODE)" tests/integration/browser_smoke.mjs

build/robotron-devices-test: tests/integration/robotron_devices_test.c $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

test: test-robotron-devices
.PHONY: test-robotron-devices
test-robotron-devices: build/robotron-devices-test
	./build/robotron-devices-test

-include $(ROBOTRON_OBJECTS:.o=.d)

build/robotron-keyboard-rom-test: tests/integration/robotron_keyboard_rom.c $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

build/dac-replay: runners/native/replay.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

.PHONY: test-clock-wasm
test-clock-wasm:
	@mkdir -p build
	emcc -O2 -std=c11 $(CPPFLAGS) tests/integration/support_test.c $(CORE) -sENVIRONMENT=node -o build/support-test.cjs
	"$(NODE)" build/support-test.cjs

test: build/dac-replay
test-wasm: test-clock-wasm

RUNTIME_BUILD_ID := $(shell git describe --always --dirty --abbrev=40 --exclude='*' 2>/dev/null || echo unversioned)
RUNTIME_SOURCES = common/runtime/session.c $(CORE) common/cpu/z80.c machines/vjuga/vjuga.c $(ROBOTRON_OBJECTS:build/%.o=%.c)
RUNTIME_HEADERS = $(wildcard common/*/*.h machines/*/*.h third_party/cpu/i8080/*.h third_party/cpu/chips/*.h)

build/libdac-runtime.so: $(RUNTIME_SOURCES) $(RUNTIME_HEADERS)
	@mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) -DDAC_BUILD_ID='"$(RUNTIME_BUILD_ID)"' -fPIC -shared $(RUNTIME_SOURCES) -o $@

.PHONY: test-verification
test-verification: build/libdac-runtime.so build/runtime-test
	python3 -m unittest discover -s tests/verification -v
	./build/runtime-test

test: test-verification

build/runtime-test: tests/integration/runtime_test.c common/runtime/session.c common/runtime/observe.h common/runtime/session.h build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) tests/integration/runtime_test.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) -o $@


build/runtime-sanitize: tests/integration/runtime_test.c $(RUNTIME_SOURCES) $(RUNTIME_HEADERS)
	@mkdir -p build
	$(CC) $(CPPFLAGS) -std=c11 -O1 -g -fsanitize=address,undefined tests/integration/runtime_test.c $(RUNTIME_SOURCES) -o $@

.PHONY: test-runtime-sanitize
test-runtime-sanitize: build/runtime-sanitize
	./build/runtime-sanitize

# Optional independent-reference check; MAME is never a normal CI dependency.
build/robotron-comparison: tests/integration/robotron_comparison.c $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@
