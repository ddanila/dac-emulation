#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
EMCC=${EMCC:-emcc}
mkdir -p dist
"$EMCC" -O2 -std=c11 common/runtime/session.c common/cpu/z80.c \
 machines/vjuga/vjuga.c machines/robotron1715m/robotron.c machines/robotron1715m/disk.c machines/robotron1715m/keyboard_board.c machines/robotron1715m/keyboard_cpu.c machines/robotron1715m/sio.c \
 machines/juku/juku.c machines/juku/juk_disk.c machines/juku/juku_fdc.c \
 third_party/cpu/i8080/i8080.c common/media/media.c common/trace/trace.c \
 -sMODULARIZE=1 -sEXPORT_ES6=1 -sENVIRONMENT=web,worker,node \
 -sALLOW_MEMORY_GROWTH=1 -sFILESYSTEM=0 -sEXPORTED_RUNTIME_METHODS=HEAPU8 \
 -sEXPORTED_FUNCTIONS='["_malloc","_free","_dac_create","_dac_debug_reg","_dac_debug_target","_dac_debug_byte","_dac_debug_map","_dac_debug_disassemble","_dac_debug_text","_dac_debug_step","_dac_debug_break","_dac_debug_hit","_dac_debug_run","_dac_destroy","_dac_load","_dac_mount","_dac_mount_unit","_dac_drive_door","_dac_drive_inserted","_dac_drive_transfer","_dac_drive_protect","_dac_disk_data_unit","_dac_disk_size_unit","_dac_drive_status_unit","_dac_drive_phase_unit","_dac_drive_steps_unit","_dac_drive_detail_unit","_dac_drive_position_unit","_dac_drive_mechanics_unit","_dac_drive_step_age","_dac_drive_diagnostic","_dac_serial_send","_dac_serial_peer","_dac_serial_peer_baud","_dac_serial_peer_format","_dac_serial_errors","_dac_serial_decoded_data","_dac_serial_decoded_size","_dac_serial_decoded_errors","_dac_serial_cancel","_dac_circuit_activity","_dac_timeline_arm","_dac_timeline_stop","_dac_timeline_status","_dac_timeline_trigger","_dac_timeline_capture","_dac_timeline_count","_dac_timeline_data","_dac_serial_signals","_dac_serial_status","_dac_serial_data","_dac_serial_size","_dac_serial_overflow","_dac_serial_clear","_dac_cables","_dac_cable_status","_dac_printer_state","_dac_printer_status","_dac_printer_dropped","_dac_printer_data","_dac_printer_size","_dac_printer_overflow","_dac_printer_clear","_dac_power","_dac_reset","_dac_run","_dac_key","_dac_width","_dac_height","_dac_video","_dac_disk_data","_dac_disk_size","_dac_disk_activity","_dac_matrix","_dac_tap","_dac_keyboard_leds","_dac_keyboard_latches","_dac_keyboard_latches_known","_dac_drive_status","_dac_state_size","_dac_state_save","_dac_state_load"]' \
 -o dist/dac.js
cp LICENSE NOTICE dist/
cp third_party/cpu/chips/LICENSE dist/chips-LICENSE
cp third_party/cpu/i8080/I8080_LICENSE dist/i8080-LICENSE
cp machines/robotron1715m/REFERENCE_LICENSE dist/robotron-reference-LICENSE
