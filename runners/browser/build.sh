#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
EMCC=${EMCC:-emcc}
mkdir -p dist
"$EMCC" -O2 -std=c11 runners/browser/dac.c common/cpu/z80.c \
 machines/vjuga/vjuga.c machines/robotron1715m/robotron.c machines/robotron1715m/keyboard.c machines/robotron1715m/sio.c \
 machines/juku/juku.c machines/juku/juk_disk.c machines/juku/juku_fdc.c \
 third_party/cpu/i8080/i8080.c common/media/media.c common/trace/trace.c \
 -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=web,worker,node \
 -sALLOW_MEMORY_GROWTH=1 -sFILESYSTEM=0 -sEXPORTED_RUNTIME_METHODS=HEAPU8 \
 -sEXPORTED_FUNCTIONS='["_malloc","_free","_dac_create","_dac_destroy","_dac_load","_dac_mount","_dac_power","_dac_reset","_dac_run","_dac_key","_dac_width","_dac_height","_dac_video","_dac_disk_data","_dac_disk_size","_dac_disk_activity","_dac_matrix","_dac_tap","_dac_keyboard_leds","_dac_drive_status","_dac_state_size","_dac_state_save","_dac_state_load"]' \
 -o dist/dac.js
cp LICENSE NOTICE dist/
cp third_party/cpu/chips/LICENSE dist/chips-LICENSE
cp third_party/cpu/i8080/I8080_LICENSE dist/i8080-LICENSE
cp machines/robotron1715m/REFERENCE_LICENSE dist/robotron-reference-LICENSE
