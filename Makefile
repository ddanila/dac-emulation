PC1715_OBJECTS = build/machines/robotron1715/pc1715.o
ROBOTRON_OBJECTS = build/machines/robotron1715m/disk.o build/machines/robotron1715m/robotron.o build/machines/robotron1715m/keyboard_board.o build/machines/robotron1715m/keyboard_cpu.o build/machines/robotron1715m/sio.o
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

build/browser-reference: tests/integration/wasm_reference.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) $(PC1715_OBJECTS)
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

build/dac-replay: runners/native/replay.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) $(PC1715_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

.PHONY: test-clock-wasm
test-clock-wasm:
	@mkdir -p build
	emcc -O2 -std=c11 $(CPPFLAGS) tests/integration/support_test.c $(CORE) -sENVIRONMENT=node -o build/support-test.cjs
	"$(NODE)" build/support-test.cjs

test: build/dac-replay
test-wasm: test-clock-wasm

RUNTIME_BUILD_ID := $(shell git describe --always --dirty --abbrev=40 --exclude='*' 2>/dev/null || echo unversioned)
RUNTIME_SOURCES = machines/robotron1715/pc1715.c common/runtime/session.c $(CORE) common/cpu/z80.c machines/vjuga/vjuga.c $(ROBOTRON_OBJECTS:build/%.o=%.c)
RUNTIME_HEADERS = $(wildcard machines/robotron1715m/generated/keyboard_cpu/*.h common/*/*.h machines/*/*.h third_party/cpu/i8080/*.h third_party/cpu/chips/*.h)

build/libdac-runtime.so: $(RUNTIME_SOURCES) $(RUNTIME_HEADERS)
	@mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) -DDAC_BUILD_ID='"$(RUNTIME_BUILD_ID)"' -fPIC -shared $(RUNTIME_SOURCES) -o $@

.PHONY: test-verification
test-verification: build/libdac-runtime.so build/runtime-test
	python3 -m unittest discover -s tests/verification -v
	./build/runtime-test

test: test-verification

build/runtime-test: tests/integration/runtime_test.c common/runtime/session.c common/runtime/observe.h common/runtime/session.h build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) $(PC1715_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) tests/integration/runtime_test.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) $(PC1715_OBJECTS) -o $@


build/runtime-sanitize: tests/integration/runtime_test.c $(RUNTIME_SOURCES) $(RUNTIME_HEADERS)
	@mkdir -p build
	$(CC) $(CPPFLAGS) -std=c11 -O1 -g -fsanitize=address,undefined tests/integration/runtime_test.c $(RUNTIME_SOURCES) -o $@

.PHONY: test-runtime-sanitize
test-runtime-sanitize: build/runtime-sanitize build/pc1715-sanitize
	./build/runtime-sanitize
	./build/pc1715-sanitize

# Optional independent-reference check; MAME is never a normal CI dependency.
build/robotron-comparison: tests/integration/robotron_comparison.c $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

build/robotron-serial-comparison: tests/integration/robotron_serial_comparison.c $(ROBOTRON_OBJECTS) build/common/cpu/z80.o build/common/media/media.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

# Optional bounded historical keyboard qualification, never a dependency of test.
.PHONY: test-s600-workload
test-s600-workload: build/runtime-test build/robotron-keyboard-rom-test
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to an external 2048-byte S600 image'; exit 2)
	./build/runtime-test --s600 "$(S600_ROM)"
	./build/robotron-keyboard-rom-test "$(S600_ROM)"

.PHONY: test-keyboard-controller audit-keyboard-controller qualify-keyboard-controller
test-keyboard-controller:
	python3 verification/robotron-keyboard/test_diagnostics.py
	python3 verification/robotron-keyboard/run.py

audit-keyboard-controller:
	python3 verification/robotron-keyboard/run.py --audit

qualify-keyboard-controller:
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to an external 2 KB keyboard ROM'; exit 2)
	python3 verification/robotron-keyboard/run.py --audit --rom "$(S600_ROM)"

.PHONY: test-keyboard-coupled-boot
KEYBOARD_BOARD_ARGS ?=
test-keyboard-coupled-boot:
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to the standard 2 KB S600 image'; exit 2)
	python3 verification/robotron-keyboard/analog/boot_cosim.py --rom "$(S600_ROM)" $(KEYBOARD_BOARD_ARGS)

.PHONY: test-keyboard-matrix-feedback
test-keyboard-matrix-feedback:
	python3 verification/robotron-keyboard/analog/matrix_cosim.py

.PHONY: test-keyboard-logic-feedback
test-keyboard-logic-feedback:
	python3 verification/robotron-keyboard/analog/logic_cosim.py $(KEYBOARD_LOGIC_ARGS)

.PHONY: test-keyboard-serial-feedback
test-keyboard-serial-feedback:
	python3 verification/robotron-keyboard/analog/serial_cosim.py

.PHONY: test-keyboard-data-drive qualify-keyboard-data-drive
test-keyboard-data-drive:
	python3 verification/robotron-keyboard/analog/bus_timing_probe.py

qualify-keyboard-data-drive: test-keyboard-data-drive
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to the standard S600 image'; exit 2)
	python3 verification/robotron-keyboard/analog/firmware_drive_compare.py --rom "$(S600_ROM)"

.PHONY: test-keyboard-resolved-bus qualify-keyboard-resolved-bus
test-keyboard-resolved-bus:
	python3 verification/robotron-keyboard/analog/resolved_bus_probe.py

qualify-keyboard-resolved-bus: test-keyboard-resolved-bus
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to the standard S600 image'; exit 2)
	python3 verification/robotron-keyboard/analog/firmware_drive_compare.py --rom "$(S600_ROM)" --resolved-bus --out build/keyboard-controller-analog/firmware-resolved-bus

.PHONY: characterize-keyboard-devices
characterize-keyboard-devices:
	python3 verification/robotron-keyboard/analog/device_probe.py

.PHONY: qualify-keyboard-firmware-io
KEYBOARD_IO_SCENARIO ?= verification/robotron-keyboard/analog/scenarios/single-press.json
KEYBOARD_IO_OUT ?= build/keyboard-controller-analog/firmware-io
KEYBOARD_IO_TIMEOUT_SECONDS ?= 1800
KEYBOARD_IO_QUALIFY_TIMEOUT_SECONDS ?= 1800
KEYBOARD_IO_COARSE_STEP_NS ?= 50
KEYBOARD_IO_FINE_STEP_NS ?= 25
KEYBOARD_IO_ARGS ?=
KEYBOARD_IO_LEDS ?= 0
KEYBOARD_IO_LED_ARGS = $(if $(filter 1,$(KEYBOARD_IO_LEDS)),--require-led-activity,)
qualify-keyboard-firmware-io:
	@test -n "$(S600_ROM)" || (echo 'Set S600_ROM to the standard S600 image'; exit 2)
	python3 verification/robotron-keyboard/analog/firmware_io_cosim.py --rom "$(S600_ROM)" --scenario "$(KEYBOARD_IO_SCENARIO)" $(KEYBOARD_IO_LED_ARGS) $(KEYBOARD_IO_ARGS) --timeout-seconds "$(KEYBOARD_IO_TIMEOUT_SECONDS)" --step-ns "$(KEYBOARD_IO_COARSE_STEP_NS)" --out "$(KEYBOARD_IO_OUT)/coarse"
	python3 verification/robotron-keyboard/analog/firmware_io_cosim.py --rom "$(S600_ROM)" --scenario "$(KEYBOARD_IO_SCENARIO)" $(KEYBOARD_IO_LED_ARGS) $(KEYBOARD_IO_ARGS) --timeout-seconds "$(KEYBOARD_IO_TIMEOUT_SECONDS)" --step-ns "$(KEYBOARD_IO_FINE_STEP_NS)" --out "$(KEYBOARD_IO_OUT)/fine"
	python3 verification/robotron-keyboard/analog/qualify_io_pair.py "$(KEYBOARD_IO_OUT)/coarse" "$(KEYBOARD_IO_OUT)/fine" --scenario "$(KEYBOARD_IO_SCENARIO)" --timeout-seconds "$(KEYBOARD_IO_QUALIFY_TIMEOUT_SECONDS)" --out "$(KEYBOARD_IO_OUT)/qualification"

.PHONY: qualify-keyboard-board-scenario
KEYBOARD_BOARD_SCENARIO ?= verification/robotron-keyboard/analog/scenarios/single-press.json
KEYBOARD_BOARD_OUT ?= build/keyboard-controller-analog/board-scenario
KEYBOARD_BOARD_TIMEOUT_SECONDS ?= 14400
KEYBOARD_BOARD_GATE_PROFILE ?= nominal
KEYBOARD_BOARD_COARSE_STEP_NS ?= 10
KEYBOARD_BOARD_FINE_STEP_NS ?= 5
qualify-keyboard-board-scenario:
	@test -n "$(S600_ROM)" || (echo "Set S600_ROM to the standard S600 image"; exit 1)
	python3 verification/robotron-keyboard/analog/boot_cosim.py --rom "$(S600_ROM)" --electrical-matrix --electrical-outputs --scenario "$(KEYBOARD_BOARD_SCENARIO)" $(KEYBOARD_BOARD_ARGS) --gate-profile "$(KEYBOARD_BOARD_GATE_PROFILE)" --timeout-seconds "$(KEYBOARD_BOARD_TIMEOUT_SECONDS)" --step-ns "$(KEYBOARD_BOARD_COARSE_STEP_NS)" --bridge-delay-ns 10 --out "$(KEYBOARD_BOARD_OUT)/coarse"
	python3 verification/robotron-keyboard/analog/boot_cosim.py --rom "$(S600_ROM)" --electrical-matrix --electrical-outputs --scenario "$(KEYBOARD_BOARD_SCENARIO)" $(KEYBOARD_BOARD_ARGS) --gate-profile "$(KEYBOARD_BOARD_GATE_PROFILE)" --timeout-seconds "$(KEYBOARD_BOARD_TIMEOUT_SECONDS)" --step-ns "$(KEYBOARD_BOARD_FINE_STEP_NS)" --bridge-delay-ns 10 --out "$(KEYBOARD_BOARD_OUT)/fine"
	python3 verification/robotron-keyboard/analog/qualify_board_pair.py "$(KEYBOARD_BOARD_OUT)/coarse" "$(KEYBOARD_BOARD_OUT)/fine" --out "$(KEYBOARD_BOARD_OUT)/qualification.json"

# Production keyboard backend; the legacy fixture is not linked into machines.
build/keyboard-backend-test: tests/integration/keyboard_backend_test.c build/machines/robotron1715m/keyboard_board.o build/machines/robotron1715m/keyboard_cpu.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

test: test-keyboard-backend
.PHONY: test-keyboard-backend
test-keyboard-backend: build/keyboard-backend-test
	python3 tools/generate_keyboard_cpu.py --check
	./build/keyboard-backend-test

-include $(PC1715_OBJECTS:.o=.d)

all: build/pc1715-probe
build/pc1715-probe: runners/native/pc1715_probe.c $(PC1715_OBJECTS) build/common/cpu/z80.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

build/pc1715-test: tests/integration/pc1715_test.c common/runtime/session.c build/libdac-juku.a $(Z80_OBJECTS) $(ROBOTRON_OBJECTS) $(PC1715_OBJECTS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

.PHONY: test-pc1715
test-pc1715: build/pc1715-test
	./build/pc1715-test

test: test-pc1715

build/pc1715-fault-probe: verification/pc1715-faults/probe.c $(PC1715_OBJECTS) build/common/cpu/z80.o build/common/trace/trace.o
	$(CC) $(CPPFLAGS) $(CFLAGS) $(WARN) $^ -o $@

.PHONY: test-pc1715-faults
test-pc1715-faults: build/pc1715-fault-probe
	python3 -m unittest discover -s verification/pc1715-faults -p 'test_*.py'

test: test-pc1715-faults

build/pc1715-sanitize: tests/integration/pc1715_test.c $(RUNTIME_SOURCES) $(RUNTIME_HEADERS)
	@mkdir -p build
	$(CC) $(CPPFLAGS) -std=c11 -O1 -g -fsanitize=address,undefined tests/integration/pc1715_test.c $(RUNTIME_SOURCES) -o $@
