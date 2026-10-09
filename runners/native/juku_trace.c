#define _XOPEN_SOURCE 600

// Traced 8080 boot harness for the Juku E5104 (ekta43.bin).
//
// Memory model is now faithful to MAME's ussr/juku.cpp (BSD-3, ref/mame_juku.cpp):
//   - 64 KB DRAM base (m_ram)
//   - a 4-way "memory view" overlays ROM, selected by 8255#0 Port C bits[1:0]
//     (I/O port 0x06, or via 8255 BSR on the control port 0x07):
//        mode 0 (reset): ROM 0x0000..0x3FFF  (region maincpu +0x0000)
//        mode 1:         ROM 0xD800..0xFFFF  (region maincpu +0x1800), rest RAM
//        mode 2:         expcart 0x4000..0xBFFF + ROM 0xD800..0xFFFF
//        mode 3:         all RAM
//   - video reads DRAM at 0xD800, normally 40 bytes/line (320x241 mono);
//     the exact MODX PIT sequence selects its 50-byte/192-line 80x24 view
//
// IN ports return the 8255 output latch when no device owns the read.  The
// functional PIC path covers frame, 8251 RxRDY, and 8251 TxRDY interrupts.
// Optional expansion cartridge: set JUKU_CART=/path/to/image.{bin,hex}.
//
// STATUS: boots the real BIOS and draws the banner to VRAM. The long-standing
// stall was the ROM self-test checksum loop (0x042C/0x0443), NOT the keyboard.
//   - ekta37.bin (official) boots cleanly -> banner (render vram.bin at stride 40).
//   - ekta43.bin (homebrew AT-kbd) has a STALE block-1 checksum (0x000A=0xF2 but
//     bytes 0x000B..0x07FF sum to 0x57); patched at load so it boots too. All 5
//     official ekta ROMs pass block-1; only ekta43 fails (confirms our checksum).
//
// Build: cc -O2 -o trace trace.c i8080.c juk_disk.c juku_fdc.c
// Run:   ./trace /path/to/ekta43.bin [max_cycles]
// USART: JUKU_USART_PTY=auto prints a new slave path; a host-created PTY path
//        may be supplied instead. JUKU_USART_TRANSFER_CYCLES controls the
//        holding-to-shift delay; JUKU_USART_BYTE_CYCLES controls frame time.
//        JUKU_STOP_PC=ADDR stops before executing ADDR after at least
//        JUKU_STOP_PC_AFTER_USART_RX bytes (useful for network-load proofs).
//        JUKU_USART_FAULT=tx_stuck accepts each post-reset byte and then holds
//        the transmit input register full until the next 8251 reset;
//        tx_stuck_once:BYTE jams one matching write until an 8251 reset;
//        tx_not_ready_once_after:COUNT jams between completed output bytes;
//        tx_empty_low_after:COUNT holds only status bit 2 low thereafter;
//        rx_irq_delay_once_after:COUNT:CYCLES delays one RxRDY interrupt long
//        enough to model a phase-sensitive ISR/overrun boundary.
// RESET: JUKU_RESET_AFTER_USART_RX=COUNT performs one board-style CPU/USART
//        reset after COUNT received bytes and replays scripted keys. This
//        exercises host bootstrap rediscovery without restarting the PTY.
// RAM:   JUKU_RAM_FAULT=ADDR:STUCK_LOW:STUCK_HIGH injects one faulty byte
//        (ADDR=* applies the stuck masks globally);
//        JUKU_RAM_ALIAS=PAGE_A:PAGE_B maps logical PAGE_B onto PAGE_A.
//        JUKU_DRAM_RETENTION_CYCLES=N deterministically inverts a complete
//        4164 refresh row if it receives no RAM access for more than N cycles.
//        Juku presents CPU A0..A6 to DRAM MA0..MA6 while /RAS is active;
//        A7/MA7 is a column-only don't-care for 128-cycle refresh.
//        JUKU_DRAM_RETENTION_ARM_PC=ADDR delays that model until the first
//        instruction at ADDR (useful when omitted video refresh is out of
//        scope and the ROM refresh service is the subject of the test).
// EXEC:  JUKU_ROM_EXEC_RESET_AT=ADDR resets the CPU whenever a ROM fetch
//        reaches ADDR or above (used to model the physical D15 A12 boundary).
// CPU:   JUKU_CPU_A12_INCREMENT_FAULT=1 makes D1's 16-bit +1 path lose an
//        already-high A12. It covers PC, INX, LHLD/SHLD, POP, and boundaries.
//        JUKU_CPU_A12_INCREMENT_FAULT_ARM_PC=ADDR enables that model when PC
//        reaches ADDR; ..._DISARM_PC=ADDR disables it again. This brackets a
//        diagnostic without corrupting the bootstrap used to reach it. Set
//        ..._ARM_BANK_MODE=0..3 when the address can also occur in an overlay.
// ROM:   JUKU_ROM_CONSECUTIVE_A12_LOW=1 retains the older ROM-local model.
// EXEC:  JUKU_EXEC_BYTE_FAULT=ADDR:VALUE overrides an instruction-stream byte
//        when the CPU PC has just advanced past ADDR; ordinary data reads pass.
// PIC:   JUKU_PIC_FAULT=STUCK_LOW:STUCK_HIGH faults the 8259 IMR readback.
// PPI:   JUKU_PPI_FAULT=PORT:STUCK_LOW:STUCK_HIGH faults D27 port readback.
// PIT:   JUKU_PIT_FAULT=PORT:STUCK_LOW:STUCK_HIGH faults D54/D55/D57 count reads.
// TERM:  JUKU_CONSOLE_PTY=auto|/dev/ttyN attaches an interactive terminal.
//        Characters the firmware writes through the ROM's WRCHR vector are
//        echoed to it, and bytes typed into it are queued as keystrokes for
//        the emulated key matrix, so `screen /dev/ttysNNN` drives the machine.
//        JUKU_CONSOLE_OUT_PC / JUKU_CONSOLE_IN_PC override the hooked ROM
//        vectors (defaults FFD9h/FFD3h, the EktaSoft monitor entries that
//        cpmish's BIOS CONOUT/CONIN call). This is a simulator affordance:
//        the real machine's console is its bitmap screen and key matrix.
//        JUKU_CONSOLE_OUT_DISABLE=1 keeps PTY keyboard input but disables the
//        output hook, for qualification through a production serial console.
// SPEED: JUKU_REALTIME_HZ=N paces execution to N simulated cycles per real
//        second, so wall-clock time equals machine time (use 2000000 for the
//        nominal Juku clock; "1" is accepted as shorthand for it). Unset means
//        run as fast as possible, which is the right default for tests.
// HOST:  JUKU_USART_HOST_SYNC_MS=N lets an unpaced PTY-backed USART wait up to
//        N wall-clock milliseconds for the first byte of a host reply after
//        target transmission. It keeps native helper processes schedulable
//        without changing simulated baud or making all execution real-time.
// CHECKPOINT: SIGUSR1 writes the configured JUKU_CHECKPOINT_PREFIX RAM/state
//        pair without stopping the machine.  The state includes the latest
//        CP/M transient's stack low-water evidence; SIGTERM/SIGINT retain their
//        existing stop-and-checkpoint behaviour. SIGUSR2 arms that evidence
//        for the next 0100h transient and freezes it at the top-level return.
// CP/M DISK: JUKU_CPM_DISK_TRACE=/path records every C6 native-BIOS READ/WRITE
//        entry, including requests satisfied by the resident cache. The fixed
//        binding is C027h/C02Ah with drive/track/sector/DMA at C93Ah; use this
//        only with the documented C000h network-ROM adapter layout.

#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t terminate_requested;
static volatile sig_atomic_t checkpoint_requests;
static volatile sig_atomic_t tpa_measurement_requests;
static int usart_fd = -1;
static FILE * video_capture_fp;
static uint8_t video_capture_previous[9640];
static int video_capture_has_previous;
static FILE * cpm_disk_trace_fp;
static unsigned long cpm_disk_trace_sequence;
static FILE * rdtrace_fp = NULL;
static unsigned long rdtrace_limit = 0;
static unsigned long rdtrace_n = 0;
static FILE * bustrace_fp = NULL;
static unsigned long bustrace_limit = 0;
static unsigned long bustrace_n = 0;
static int console_fd = -1;
static unsigned long console_poll_at = 0;
static uint16_t console_out_pc = 0xD9E3;
static uint16_t console_in_pc = 0xFFD3;
static int console_out_register_c = 0;
static int console_out_enabled = 1;

static void request_termination(int signal_number) {
  (void)signal_number;
  terminate_requested = 1;
}

static void request_checkpoint(int signal_number) {
  (void)signal_number;
  if (checkpoint_requests < 0x7FFF)
    checkpoint_requests++;
}

static void request_tpa_measurement(int signal_number) {
  (void)signal_number;
  if (tpa_measurement_requests < 0x7FFF)
    tpa_measurement_requests++;
}

static int env_enabled(const char* value) {
  return value && value[0] && strcmp(value, "0") != 0;
}

static int set_raw_tty(int fd) {
  struct termios tty;
  if (tcgetattr(fd, &tty) != 0) return -1;
  tty.c_iflag &= (tcflag_t)~(IGNBRK | BRKINT | PARMRK | ISTRIP |
                             INLCR | IGNCR | ICRNL | IXON);
  tty.c_oflag &= (tcflag_t)~OPOST;
  tty.c_lflag &= (tcflag_t)~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
  tty.c_cflag &= (tcflag_t)~(CSIZE | PARENB);
  tty.c_cflag |= CS8 | CLOCAL | CREAD;
  tty.c_cc[VMIN] = 0;
  tty.c_cc[VTIME] = 0;
  return tcsetattr(fd, TCSANOW, &tty);
}

static int set_nonblocking(int fd) {
  int flags = fcntl(fd, F_GETFL, 0);
  return flags < 0 ? -1 : fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static int open_serial_endpoint(const char* setting, const char* tag) {
  int fd;
  if (strcmp(setting, "auto") == 0) {
    fd = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0 || grantpt(fd) != 0 || unlockpt(fd) != 0) {
      if (fd >= 0) close(fd);
      return -1;
    }
    char* slave_name = ptsname(fd);
    if (!slave_name) {
      close(fd);
      return -1;
    }
    int slave = open(slave_name, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (slave < 0 || set_raw_tty(slave) != 0) {
      if (slave >= 0) close(slave);
      close(fd);
      return -1;
    }
    close(slave);
    fprintf(stderr, "[%s] PTY slave=%s\n", tag, slave_name);
  } else {
    fd = open(setting, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0 || set_raw_tty(fd) != 0) {
      if (fd >= 0) close(fd);
      return -1;
    }
    fprintf(stderr, "[%s] attached PTY=%s\n", tag, setting);
  }
  if (set_nonblocking(fd) != 0) {
    close(fd);
    return -1;
  }
  return fd;
}

static int usart_open_transport(juku *ctx, const char* setting) {
  if (!setting || !setting[0]) return 0;
  int fd = open_serial_endpoint(setting, "USART");
  if (fd < 0) return -1;
  usart_fd = fd;
  ctx->usart.enabled = 1;
  return 0;
}

static void console_poll(juku *ctx) {
  if (console_fd < 0) return;
  char buffer[256];
  ssize_t got = read(console_fd, buffer, sizeof(buffer));
  if (got <= 0) return;
  for (ssize_t i = 0; i < got; i++) {
    char c = buffer[i] == '\n' ? '\r' : buffer[i];
    if (c == 0x7F) c = '\b';                       // terminal DEL -> backspace
    if (ctx->console_len + 2 >= CONSOLE_QUEUE) {
      // Compact: drop what the matrix has already consumed.
      if (ctx->kbd_pos > 0 && ctx->kbd_pos <= ctx->console_len) {
        memmove(ctx->console_queue, ctx->console_queue + ctx->kbd_pos,
                (size_t)(ctx->console_len - ctx->kbd_pos));
        ctx->console_len -= ctx->kbd_pos;
        ctx->console_visible_len = ctx->console_visible_len > ctx->kbd_pos
            ? ctx->console_visible_len - ctx->kbd_pos : 0;
        ctx->kbd_pos = 0;
      } else {
        return;                                    // full and nothing consumed
      }
    }
    ctx->console_queue[ctx->console_len++] = c;
    ctx->console_queue[ctx->console_len] = 0;
  }
  ctx->kbd_str = ctx->console_queue;
  ctx->kbd_enabled = 1;
}

static void capture_video_frame(juku *ctx, unsigned long cycle) {
  if (!video_capture_fp) return;
  size_t size = (size_t)ctx->video_stride * ctx->video_lines;
  const uint8_t* frame = &ctx->ram[VRAM_BASE];
  if (video_capture_has_previous &&
      memcmp(video_capture_previous, frame, size) == 0) return;
  (void)cycle;
  struct timespec captured_at;
  clock_gettime(CLOCK_MONOTONIC, &captured_at);
  uint64_t timestamp = (uint64_t)captured_at.tv_sec * 1000000000u +
      (uint64_t)captured_at.tv_nsec;
  uint16_t stride = (uint16_t)ctx->video_stride;
  uint16_t lines = (uint16_t)ctx->video_lines;
  if (fwrite(&timestamp, sizeof(timestamp), 1, video_capture_fp) != 1 ||
      fwrite(&stride, sizeof(stride), 1, video_capture_fp) != 1 ||
      fwrite(&lines, sizeof(lines), 1, video_capture_fp) != 1 ||
      fwrite(frame, 1, size, video_capture_fp) != size) {
    fprintf(stderr, "[VIDEO] capture write failed\n");
    fclose(video_capture_fp);
    video_capture_fp = NULL;
    return;
  }
  memcpy(video_capture_previous, frame, size);
  video_capture_has_previous = 1;
}

static uint8_t sum_block(const uint8_t* r) {   // block-1 checksum (0x000B..0x07FF)
  unsigned s = 0; for (int i = 0x0B; i < 0x800; i++) s += r[i]; return s & 0xFF;
}

static int has_suffix(const char* path, const char* suffix) {
  size_t plen = strlen(path), slen = strlen(suffix);
  return plen >= slen && strcmp(path + plen - slen, suffix) == 0;
}

static size_t load_image(const char* path, uint8_t* dst, size_t cap, int fill) {
  memset(dst, fill, cap);
  FILE* f = fopen(path, "r");
  if (!f) { perror(path); exit(1); }
  size_t n = 0;
  if (has_suffix(path, ".hex")) {
    unsigned byte;
    while (n < cap && fscanf(f, "%x", &byte) == 1)
      dst[n++] = (uint8_t)byte;
  } else {
    fclose(f);
    f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    n = fread(dst, 1, cap, f);
  }
  fclose(f);
  return n;
}

static void dump_checkpoint(juku *ctx, const char* prefix, const i8080* cpu) {
  if (!prefix || !prefix[0]) return;

  ctx->checkpoint_generation++;

  char ram_path[1024];
  char state_path[1024];
  snprintf(ram_path, sizeof(ram_path), "%s.ram", prefix);
  snprintf(state_path, sizeof(state_path), "%s.state", prefix);

  FILE* ram_out = fopen(ram_path, "wb");
  if (!ram_out) {
    perror(ram_path);
    exit(1);
  }
  fwrite(ctx->ram, 1, sizeof(ctx->ram), ram_out);
  fclose(ram_out);

  FILE* state_out = fopen(state_path, "w");
  if (!state_out) {
    perror(state_path);
    exit(1);
  }
  fprintf(state_out, "pc=%04X\n", cpu->pc);
  fprintf(state_out, "sp=%04X\n", cpu->sp);
  fprintf(state_out, "a=%02X\n", cpu->a);
  fprintf(state_out, "b=%02X\n", cpu->b);
  fprintf(state_out, "c=%02X\n", cpu->c);
  fprintf(state_out, "d=%02X\n", cpu->d);
  fprintf(state_out, "e=%02X\n", cpu->e);
  fprintf(state_out, "h=%02X\n", cpu->h);
  fprintf(state_out, "l=%02X\n", cpu->l);
  fprintf(state_out, "sf=%u\n", cpu->sf ? 1 : 0);
  fprintf(state_out, "zf=%u\n", cpu->zf ? 1 : 0);
  fprintf(state_out, "hf=%u\n", cpu->hf ? 1 : 0);
  fprintf(state_out, "pf=%u\n", cpu->pf ? 1 : 0);
  fprintf(state_out, "cf=%u\n", cpu->cf ? 1 : 0);
  fprintf(state_out, "iff=%u\n", cpu->iff ? 1 : 0);
  fprintf(state_out, "halted=%u\n", cpu->halted ? 1 : 0);
  fprintf(state_out, "interrupt_pending=%u\n", cpu->interrupt_pending ? 1 : 0);
  fprintf(state_out, "interrupt_vector=%02X\n", cpu->interrupt_vector);
  fprintf(state_out, "interrupt_delay=%02X\n", cpu->interrupt_delay);
  fprintf(state_out, "cyc=%lu\n", cpu->cyc);
  fprintf(state_out, "checkpoint_generation=%lu\n", ctx->checkpoint_generation);
  fprintf(state_out, "tpa_opcode_fetches=%lu\n", ctx->tpa_opcode_fetches);
  fprintf(state_out, "tpa_z80_prefix_fetches=%lu\n",
          ctx->tpa_z80_prefix_fetches);
  fprintf(state_out, "tpa_undocumented_opcode_fetches=%lu\n",
          ctx->tpa_undocumented_opcode_fetches);
  fprintf(state_out, "tpa_program_starts=%lu\n", ctx->tpa_program_starts);
  fprintf(state_out, "tpa_program_entry_sp=%04X\n", ctx->tpa_program_entry_sp);
  fprintf(state_out, "tpa_program_stack_anchor_sp=%04X\n",
          ctx->tpa_program_stack_anchor_sp);
  fprintf(state_out, "tpa_program_stack_low_sp=%04X\n",
          ctx->tpa_program_stack_low_sp);
  fprintf(state_out, "tpa_program_segment_min_anchor_sp=%04X\n",
          ctx->tpa_program_segment_min_anchor_sp);
  fprintf(state_out, "tpa_program_segment_max_anchor_sp=%04X\n",
          ctx->tpa_program_segment_max_anchor_sp);
  fprintf(state_out, "tpa_program_stack_segments=%u\n",
          ctx->tpa_program_stack_segments);
  fprintf(state_out, "tpa_program_stack_bytes=%u\n",
          ctx->tpa_program_stack_bytes);
  fprintf(state_out, "tpa_program_explicit_sp_writes=%u\n",
          ctx->tpa_program_explicit_sp_writes);
  fprintf(state_out, "tpa_program_call_depth=%u\n",
          ctx->tpa_program_call_depth);
  fprintf(state_out, "tpa_program_in_bdos=%d\n", ctx->tpa_program_in_bdos);
  fprintf(state_out, "tpa_program_bdos_tail_call=%d\n",
          ctx->tpa_program_bdos_tail_call);
  fprintf(state_out, "tpa_measurement_generation=%lu\n",
          ctx->tpa_measurement_generation);
  fprintf(state_out, "tpa_measurement_armed=%d\n", ctx->tpa_measurement_armed);
  fprintf(state_out, "tpa_measurement_frozen=%d\n", ctx->tpa_measurement_frozen);
  fprintf(state_out, "vram_writes=%lu\n", ctx->g_vw);
  fprintf(state_out, "watch_write_count=%lu\n", ctx->watch_write_count);
  fprintf(state_out, "watch_write_previous_address=%04X\n",
          ctx->watch_write_previous_address);
  fprintf(state_out, "watch_write_previous_value=%02X\n",
          ctx->watch_write_previous_value);
  fprintf(state_out, "watch_write_previous_pc=%04X\n",
          ctx->watch_write_previous_pc);
  fprintf(state_out, "watch_write_previous_cycle=%lu\n",
          ctx->watch_write_previous_cycle);
  fprintf(state_out, "watch_write_last_address=%04X\n",
          ctx->watch_write_last_address);
  fprintf(state_out, "watch_write_last_value=%02X\n",
          ctx->watch_write_last_value);
  fprintf(state_out, "watch_write_last_pc=%04X\n", ctx->watch_write_last_pc);
  fprintf(state_out, "watch_write_last_cycle=%lu\n",
          ctx->watch_write_last_cycle);
  fprintf(state_out, "mode=%d\n", ctx->mode);
  fprintf(state_out, "portc=%02X\n", ctx->portc);
  fprintf(state_out, "video_pof_released=%u\n", (ctx->portc & 0x80u) ? 0u : 1u);
  fprintf(state_out, "mode_switches=%lu\n", ctx->mode_switches);
  fprintf(state_out, "video_stride=%u\n", ctx->video_stride);
  fprintf(state_out, "video_lines=%u\n", ctx->video_lines);
  fprintf(state_out, "video_modx_mode=%d\n", ctx->video_modx_mode);
  fprintf(state_out, "video_console_mode=%u\n", ctx->video_console_mode);
  fprintf(state_out, "rom_consecutive_a12_low=%d\n",
          ctx->rom_consecutive_a12_low);
  fprintf(state_out, "rom_read_burst_count=%u\n", ctx->rom_read_burst_count);
  fprintf(state_out, "cpu_a12_increment_fault=%d\n",
          ctx->cpu_a12_increment_fault);
  fprintf(state_out, "cpu_a12_increment_fault_arm_fired=%d\n",
          ctx->cpu_a12_increment_fault_arm_fired);
  fprintf(state_out, "cpu_a12_increment_fault_disarm_fired=%d\n",
          ctx->cpu_a12_increment_fault_disarm_fired);
  fprintf(state_out, "exec_byte_fault_enabled=%d\n", ctx->exec_byte_fault_enabled);
  fprintf(state_out, "exec_byte_fault_addr=%04X\n", ctx->exec_byte_fault_addr);
  fprintf(state_out, "exec_byte_fault_value=%02X\n", ctx->exec_byte_fault_value);
  fprintf(state_out, "ram_fault_enabled=%d\n", ctx->ram_fault_enabled);
  fprintf(state_out, "ram_fault_addr=%04X\n", ctx->ram_fault_addr);
  fprintf(state_out, "ram_fault_stuck_low=%02X\n", ctx->ram_fault_stuck_low);
  fprintf(state_out, "ram_fault_stuck_high=%02X\n", ctx->ram_fault_stuck_high);
  fprintf(state_out, "ram_fault_all=%d\n", ctx->ram_fault_all);
  fprintf(state_out, "ram_alias_enabled=%d\n", ctx->ram_alias_enabled);
  fprintf(state_out, "ram_alias_page_a=%02X\n", ctx->ram_alias_page_a);
  fprintf(state_out, "ram_alias_page_b=%02X\n", ctx->ram_alias_page_b);
  fprintf(state_out, "dram_retention_cycles=%lu\n", ctx->dram_retention_cycles);
  fprintf(state_out, "dram_decay_count=%lu\n", ctx->dram_decay_count);
  fprintf(state_out, "dram_coverage_count=%u\n", ctx->dram_coverage_count);
  fprintf(state_out, "dram_full_coverage_reported=%d\n",
          ctx->dram_full_coverage_reported);
  fprintf(state_out, "kbd_pos=%d\n", ctx->kbd_pos);
  fprintf(state_out, "kbd_phase=%d\n", ctx->kbd_phase);
  fprintf(state_out, "kbd_col=%02X\n", ctx->kbd_col);
  fprintf(state_out, "pic_icw1=%02X\n", ctx->pic_icw1);
  fprintf(state_out, "pic_icw2=%02X\n", ctx->pic_icw2);
  fprintf(state_out, "pic_mask=%02X\n", ctx->pic_mask);
  fprintf(state_out, "pic_expect_icw2=%d\n", ctx->pic_expect_icw2);
  fprintf(state_out, "pic_usart_rx_irq_count=%lu\n", ctx->usart_rx_irq_count);
  fprintf(state_out, "pic_usart_tx_irq_count=%lu\n", ctx->usart_tx_irq_count);
  fprintf(state_out, "pic_frame_irq_count=%lu\n", ctx->frame_irq_count);
  fprintf(state_out, "pic_fault_enabled=%d\n", ctx->pic_fault_enabled);
  fprintf(state_out, "pic_fault_stuck_low=%02X\n", ctx->pic_fault_stuck_low);
  fprintf(state_out, "pic_fault_stuck_high=%02X\n", ctx->pic_fault_stuck_high);
  fprintf(state_out, "ppi1_control=%02X\n", ctx->out_last[0x0F]);
  fprintf(state_out, "ppi1_pa_latch=%02X\n", ctx->out_last[0x0C]);
  fprintf(state_out, "ppi1_pb_latch=%02X\n", ctx->out_last[0x0D]);
  fprintf(state_out, "ppi1_pc_latch=%02X\n", ctx->out_last[0x0E]);
  fprintf(state_out, "ppi_fault_enabled=%d\n", ctx->ppi_fault_enabled);
  fprintf(state_out, "ppi_fault_port=%02X\n", ctx->ppi_fault_port);
  fprintf(state_out, "ppi_fault_stuck_low=%02X\n", ctx->ppi_fault_stuck_low);
  fprintf(state_out, "ppi_fault_stuck_high=%02X\n", ctx->ppi_fault_stuck_high);
  fprintf(state_out, "pit_fault_enabled=%d\n", ctx->pit_fault_enabled);
  fprintf(state_out, "pit_fault_port=%02X\n", ctx->pit_fault_port);
  fprintf(state_out, "pit_fault_stuck_low=%02X\n", ctx->pit_fault_stuck_low);
  fprintf(state_out, "pit_fault_stuck_high=%02X\n", ctx->pit_fault_stuck_high);
  fprintf(state_out, "fdc_enabled=%d\n", ctx->fdc_enabled);
  fprintf(state_out, "fdc_bus_invert=%d\n", ctx->fdc_bus_invert);
  fprintf(state_out, "fdc_head=%d\n", ctx->fdc.head);
  fprintf(state_out, "fdc_drive=%d\n", ctx->fdc.drive);
  fprintf(state_out, "fdc_motor_on=%d\n", ctx->fdc.motor_on);
  fprintf(state_out, "fdc_status=%02X\n", ctx->fdc.status);
  fprintf(state_out, "fdc_track=%02X\n", ctx->fdc.track);
  fprintf(state_out, "fdc_physical_track=%02X\n", ctx->fdc.physical_track);
  fprintf(state_out, "fdc_sector=%02X\n", ctx->fdc.sector);
  fprintf(state_out, "fdc_data=%02X\n", ctx->fdc.data);
  fprintf(state_out, "fdc_command=%02X\n", ctx->fdc.command);
  fprintf(state_out, "fdc_buffer_pos=%u\n", ctx->fdc.buffer_pos);
  fprintf(state_out, "fdc_buffer_len=%u\n", ctx->fdc.buffer_len);
  fprintf(state_out, "fdc_drq_ticks=%u\n", ctx->fdc.drq_ticks);
  fprintf(state_out, "fdc_write_first_byte_pending=%d\n", ctx->fdc.write_first_byte_pending);
  fprintf(state_out, "fdc_data_reads=%lu\n", ctx->fdc_data_reads);
  fprintf(state_out, "usart_enabled=%d\n", ctx->usart.enabled);
  fprintf(state_out, "usart_mode=%02X\n", ctx->usart.mode_word);
  fprintf(state_out, "usart_command=%02X\n", ctx->usart.command);
  fprintf(state_out, "usart_status=%02X\n", juku_usart_status(ctx));
  fprintf(state_out, "usart_tx_holding_full=%d\n", ctx->usart.tx_holding_full);
  fprintf(state_out, "usart_tx_shift_busy=%d\n", ctx->usart.tx_busy);
  fprintf(state_out, "usart_fault_tx_stuck=%d\n", ctx->usart.fault_tx_stuck);
  fprintf(state_out, "usart_fault_tx_stuck_permanent=%d\n", ctx->usart.fault_tx_stuck_permanent);
  fprintf(state_out, "usart_fault_tx_stuck_once_enabled=%d\n", ctx->usart.fault_tx_stuck_once_enabled);
  fprintf(state_out, "usart_fault_tx_stuck_once_fired=%d\n", ctx->usart.fault_tx_stuck_once_fired);
  fprintf(state_out, "usart_fault_tx_stuck_once_value=%02X\n", ctx->usart.fault_tx_stuck_once_value);
  fprintf(state_out, "usart_fault_tx_not_ready_once_after_enabled=%d\n", ctx->usart.fault_tx_not_ready_once_after_enabled);
  fprintf(state_out, "usart_fault_tx_not_ready_once_after=%lu\n", ctx->usart.fault_tx_not_ready_once_after);
  fprintf(state_out, "usart_fault_tx_empty_low_after_enabled=%d\n", ctx->usart.fault_tx_empty_low_after_enabled);
  fprintf(state_out, "usart_fault_tx_empty_low_after=%lu\n", ctx->usart.fault_tx_empty_low_after);
  fprintf(state_out, "usart_fault_tx_stuck_once_recoveries=%lu\n", ctx->usart.fault_tx_stuck_once_recoveries);
  fprintf(state_out, "usart_tx_bytes=%lu\n", ctx->usart.tx_bytes);
  fprintf(state_out, "usart_rx_bytes=%lu\n", ctx->usart.rx_bytes);
  fprintf(state_out, "usart_rx_overruns=%lu\n", ctx->usart.rx_overruns);
  fprintf(state_out, "usart_rx_overruns_at_all_ram=%lu\n",
          ctx->usart.rx_overruns_at_all_ram);
  fprintf(state_out, "usart_rx_overruns_in_all_ram=%lu\n",
          ctx->usart.rx_overruns - ctx->usart.rx_overruns_at_all_ram);
  fprintf(state_out, "usart_rx_disabled_bytes=%lu\n",
          ctx->usart.rx_disabled_bytes);
  fprintf(state_out, "usart_rx_next_cyc=%lu\n", ctx->usart.rx_next_cyc);
  fprintf(state_out, "usart_tx_irq_armed=%d\n", ctx->usart_tx_irq_armed);
  fprintf(state_out, "usart_tx_irq_pending=%d\n", ctx->usart_tx_irq_pending);
  fprintf(state_out, "usart_rx_irq_pending=%d\n", ctx->usart_rx_irq_pending);
  fprintf(state_out, "usart_rx_irq_delay_once_enabled=%d\n",
          ctx->usart.fault_rx_irq_delay_once_enabled);
  fprintf(state_out, "usart_rx_irq_delay_once_fired=%d\n",
          ctx->usart.fault_rx_irq_delay_once_fired);
  fprintf(state_out, "usart_rx_irq_delay_once_after=%lu\n",
          ctx->usart.fault_rx_irq_delay_once_after);
  fprintf(state_out, "usart_rx_irq_delay_cycles=%lu\n",
          ctx->usart.fault_rx_irq_delay_cycles);
  for (int p = 0; p < 256; p++) {
    if (ctx->out_count[p] || ctx->in_count[p] || ctx->out_last[p])
      fprintf(state_out, "port_%02X=last:%02X,out:%lu,in:%lu\n",
              p, ctx->out_last[p], ctx->out_count[p], ctx->in_count[p]);
  }
  fclose(state_out);
  fprintf(stderr, "[CHECKPOINT] wrote %s and %s\n", ram_path, state_path);
}

static unsigned long stop_prompt_after_rx;
static int stop_prompt_hit;

static int host_serial_read(void *user, void *bytes, size_t size) {
  (void)user;
  ssize_t result = read(usart_fd, bytes, size);
  if (result < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EIO) {
    perror("JUKU USART PTY read"); exit(2);
  }
  return result > 0 ? (int)result : 0;
}
static int host_serial_write(void *user, uint8_t byte) {
  (void)user;
  ssize_t result = write(usart_fd, &byte, 1);
  if (result < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EIO) {
    perror("JUKU USART PTY write"); exit(2);
  }
  return result == 1;
}
static int host_serial_wait(void *user, int milliseconds) {
  (void)user;
  struct pollfd descriptor = {usart_fd, POLLIN, 0};
  int ready;
  do { ready = poll(&descriptor, 1, milliseconds); }
  while (ready < 0 && errno == EINTR && !terminate_requested);
  if (ready < 0 && errno != EINTR) { perror("JUKU USART PTY host sync"); exit(2); }
  return ready > 0 && (descriptor.revents & POLLIN);
}
static void host_log(void *user, const char *message) {
  (void)user; fputs(message, stderr);
}
static void host_memory_read(void *user, uint16_t a, uint8_t v) {
  (void)user;
  if (!rdtrace_fp) return;
  fprintf(rdtrace_fp, "%04x %02x\n", a, v);
  if (rdtrace_limit && ++rdtrace_n >= rdtrace_limit) { fclose(rdtrace_fp); rdtrace_fp = NULL; }
}
static void host_bus_trace(void *user, const dac_trace_event *event) {
  (void)user;
  if (!bustrace_fp) return;
  fprintf(bustrace_fp, "%s %04x %02x\n", event->kind, event->address, event->data);
  if (bustrace_limit && ++bustrace_n >= bustrace_limit) { fclose(bustrace_fp); bustrace_fp = NULL; }
}
static void host_frame(void *user, unsigned long cycle) {
  juku *ctx = user;
  if (stop_prompt_after_rx && ctx->usart.rx_bytes >= stop_prompt_after_rx &&
      juku_ekdos_prompt_visible(ctx)) stop_prompt_hit = 1;
  capture_video_frame(ctx, cycle);
}

int main(int argc, char** argv) {
  juku *ctx = juku_create();
  if (!ctx) return 2;
  ctx->hooks = (juku_hooks){ctx, host_serial_read, host_serial_write,
      host_serial_wait, host_memory_read, host_log, host_frame};
  ctx->bus_trace.emit = host_bus_trace;
  ctx->bus_trace.user = ctx;
  signal(SIGTERM, request_termination);
  signal(SIGINT, request_termination);
  struct sigaction checkpoint_action;
  memset(&checkpoint_action, 0, sizeof(checkpoint_action));
  checkpoint_action.sa_handler = request_checkpoint;
  sigemptyset(&checkpoint_action.sa_mask);
  checkpoint_action.sa_flags = SA_RESTART;
  if (sigaction(SIGUSR1, &checkpoint_action, NULL) != 0) {
    perror("sigaction(SIGUSR1)");
    return 2;
  }
  struct sigaction measurement_action;
  memset(&measurement_action, 0, sizeof(measurement_action));
  measurement_action.sa_handler = request_tpa_measurement;
  sigemptyset(&measurement_action.sa_mask);
  measurement_action.sa_flags = SA_RESTART;
  if (sigaction(SIGUSR2, &measurement_action, NULL) != 0) {
    perror("sigaction(SIGUSR2)");
    return 2;
  }
  juku_pit_init(ctx);
  const char* rom_path = argc > 1 ? argv[1] : "ekta43.bin";
  unsigned long max_cyc = argc > 2 ? strtoul(argv[2], 0, 0) : 50000000UL;
  ctx->g_vw_limit            = argc > 3 ? strtoul(argv[3], 0, 0) : 0UL;   // 0 = no video-write limit
  ctx->frame_cyc = argc > 4 ? strtoul(argv[4], 0, 0) : 0UL; // frame-interrupt period (cycles); 0 = off
  const char* video_capture_path = getenv("JUKU_VIDEO_CAPTURE");
  if (video_capture_path && video_capture_path[0]) {
    video_capture_fp = fopen(video_capture_path, "wb");
    if (!video_capture_fp) {
      fprintf(stderr, "cannot open JUKU_VIDEO_CAPTURE=%s: %s\n",
              video_capture_path, strerror(errno));
      return 2;
    }
  }
  const char* checkpoint_cyc_env = getenv("JUKU_CHECKPOINT_CYC");
  unsigned long checkpoint_cyc = (checkpoint_cyc_env && checkpoint_cyc_env[0]) ? strtoul(checkpoint_cyc_env, 0, 0) : 0UL;
  const char* stop_pc_env = getenv("JUKU_STOP_PC");
  const char* stop_pc_rx_env = getenv("JUKU_STOP_PC_AFTER_USART_RX");
  int stop_pc_enabled = 0;
  unsigned long stop_pc = 0, stop_pc_after_usart_rx = 0;
  const char* reset_after_rx_env = getenv("JUKU_RESET_AFTER_USART_RX");
  unsigned long reset_after_rx = 0;
  int reset_after_rx_fired = 0;
  if (reset_after_rx_env && reset_after_rx_env[0]) {
    char* end = NULL;
    reset_after_rx = strtoul(reset_after_rx_env, &end, 0);
    if (!end || *end || !reset_after_rx) {
      fprintf(stderr,
              "invalid JUKU_RESET_AFTER_USART_RX=%s (expected positive count)\n",
              reset_after_rx_env);
      return 2;
    }
  }
  if (stop_pc_env && stop_pc_env[0]) {
    char* end = NULL;
    stop_pc = strtoul(stop_pc_env, &end, 0);
    if (!end || *end || stop_pc > 0xFFFF) {
      fprintf(stderr, "invalid JUKU_STOP_PC=%s (expected 0..0xFFFF)\n",
              stop_pc_env);
      return 2;
    }
    stop_pc_enabled = 1;
    if (stop_pc_rx_env && stop_pc_rx_env[0]) {
      end = NULL;
      stop_pc_after_usart_rx = strtoul(stop_pc_rx_env, &end, 0);
      if (!end || *end) {
        fprintf(stderr,
                "invalid JUKU_STOP_PC_AFTER_USART_RX=%s "
                "(expected byte count)\n",
                stop_pc_rx_env);
        return 2;
      }
    }
  }
  const char* rom_exec_reset_env = getenv("JUKU_ROM_EXEC_RESET_AT");
  unsigned long rom_exec_reset_at = 0;
  unsigned long rom_exec_resets = 0;
  if (rom_exec_reset_env && rom_exec_reset_env[0]) {
    char* end = NULL;
    rom_exec_reset_at = strtoul(rom_exec_reset_env, &end, 0);
    if (!end || *end || rom_exec_reset_at == 0 || rom_exec_reset_at > 0x3FFF) {
      fprintf(stderr,
              "invalid JUKU_ROM_EXEC_RESET_AT=%s (expected 1..0x3FFF)\n",
              rom_exec_reset_env);
      return 2;
    }
  }
  const char* stop_keys_done_env = getenv("JUKU_STOP_KEYS_DONE");
  int stop_keys_done = stop_keys_done_env && stop_keys_done_env[0] &&
                       strcmp(stop_keys_done_env, "0") != 0;
  const char* disable_settle_env = getenv("JUKU_DISABLE_SETTLE");
  int disable_settle = env_enabled(disable_settle_env);
  const char* stop_prompt_rx_env = getenv("JUKU_STOP_PROMPT_AFTER_USART_RX");
  stop_prompt_after_rx = stop_prompt_rx_env && stop_prompt_rx_env[0]
      ? strtoul(stop_prompt_rx_env, NULL, 0) : 0;
  stop_prompt_hit = 0;
  ctx->next_frame = ctx->frame_cyc;
  ctx->kbd_str = getenv("JUKU_KEYS");     // keystrokes to type (needs frame interrupt on); unset = keyboard off
  const char* kbd_enabled_env = getenv("JUKU_KEYBOARD_ENABLE");
  const char* kbd_s21_env = getenv("JUKU_S21_CONFIG");
  if (kbd_s21_env && kbd_s21_env[0]) {
    char* end = NULL;
    unsigned long parsed = strtoul(kbd_s21_env, &end, 0);
    if (!end || *end || parsed > 0xFF) {
      fprintf(stderr, "invalid JUKU_S21_CONFIG=%s (expected 0..255)\n",
              kbd_s21_env);
      return 2;
    }
    ctx->kbd_s21_config = (uint8_t)parsed;
  }
  ctx->kbd_enabled = (ctx->kbd_str && ctx->kbd_str[0]) ||
                (kbd_s21_env && kbd_s21_env[0]) ||
                (kbd_enabled_env && kbd_enabled_env[0] && strcmp(kbd_enabled_env, "0") != 0);
  const char* kbd_start_vram_env = getenv("JUKU_KEY_START_VRAM");
  if (kbd_start_vram_env && kbd_start_vram_env[0]) ctx->kbd_start_vram = strtoul(kbd_start_vram_env, 0, 0);
  const char* kbd_hold_env = getenv("JUKU_KEY_HOLD_FRAMES");
  if (kbd_hold_env && kbd_hold_env[0]) ctx->kbd_hold_frames = atoi(kbd_hold_env);
  const char* kbd_gap_env = getenv("JUKU_KEY_GAP_FRAMES");
  if (kbd_gap_env && kbd_gap_env[0]) ctx->kbd_gap_frames = atoi(kbd_gap_env);
  const char* kbd_at_pc_env = getenv("JUKU_KEY_AT_PC");
  if (kbd_at_pc_env && kbd_at_pc_env[0]) {
    unsigned long pc = 0, key = 0;
    char trailing = 0;
    if (sscanf(kbd_at_pc_env, "%lx:%lx%c", &pc, &key, &trailing) != 2 ||
        pc > 0xFFFF || key == 0 || key > 0xFF) {
      fprintf(stderr,
              "invalid JUKU_KEY_AT_PC=%s (expected 0000..FFFF:01..FF)\n",
              kbd_at_pc_env);
      return 2;
    }
    ctx->kbd_pc_trigger_enabled = 1;
    ctx->kbd_pc_trigger_pc = (uint16_t)pc;
    ctx->kbd_pc_trigger_char = (char)key;
    ctx->kbd_enabled = 1;
  }
  const char* kbd_at_pc_hold_env = getenv("JUKU_KEY_AT_PC_HOLD_FRAMES");
  if (kbd_at_pc_hold_env && kbd_at_pc_hold_env[0])
    ctx->kbd_pc_trigger_hold_frames = atoi(kbd_at_pc_hold_env);
  const char* kbd_at_pc_gate_env = getenv("JUKU_KEY_AT_PC_GATE");
  if (kbd_at_pc_gate_env && kbd_at_pc_gate_env[0]) {
    unsigned long address = 0, value = 0;
    char trailing = 0;
    if (sscanf(kbd_at_pc_gate_env, "%lx:%lx%c", &address, &value,
               &trailing) != 2 || address > 0xFFFF || value > 0xFF) {
      fprintf(stderr,
              "invalid JUKU_KEY_AT_PC_GATE=%s "
              "(expected 0000..FFFF:00..FF)\n",
              kbd_at_pc_gate_env);
      return 2;
    }
    ctx->kbd_pc_trigger_gate_enabled = 1;
    ctx->kbd_pc_trigger_gate_address = (uint16_t)address;
    ctx->kbd_pc_trigger_gate_value = (uint8_t)value;
  }
  ctx->kbd_trace = getenv("JUKU_TRACE_KBD") && getenv("JUKU_TRACE_KBD")[0] &&
              strcmp(getenv("JUKU_TRACE_KBD"), "0") != 0;
  if (ctx->kbd_hold_frames < 1) ctx->kbd_hold_frames = KBD_HOLD;
  if (ctx->kbd_gap_frames < 1) ctx->kbd_gap_frames = KBD_GAP;
  if (ctx->kbd_pc_trigger_hold_frames < 1)
    ctx->kbd_pc_trigger_hold_frames = ctx->kbd_hold_frames;
  const char* stop_fdc_data_reads_env = getenv("JUKU_STOP_FDC_DATA_READS");
  if (stop_fdc_data_reads_env && stop_fdc_data_reads_env[0])
    ctx->stop_fdc_data_reads = strtoul(stop_fdc_data_reads_env, 0, 0);
  const char* rdtrace_path = getenv("JUKU_RDTRACE");
  if (rdtrace_path && rdtrace_path[0]) {
    rdtrace_fp = fopen(rdtrace_path, "w");
    if (!rdtrace_fp) fprintf(stderr, "JUKU_RDTRACE=%s could not be opened for writing\n", rdtrace_path);
    const char* rdtrace_limit_env = getenv("JUKU_RDTRACE_LIMIT");
    if (rdtrace_limit_env && rdtrace_limit_env[0]) rdtrace_limit = strtoul(rdtrace_limit_env, 0, 0);
  }
  const char* bustrace_path = getenv("JUKU_BUS_TRACE");
  if (bustrace_path && bustrace_path[0]) {
    bustrace_fp = fopen(bustrace_path, "w");
    if (!bustrace_fp) {
      fprintf(stderr, "JUKU_BUS_TRACE=%s could not be opened for writing\n", bustrace_path);
      return 2;
    }
    const char* bustrace_limit_env = getenv("JUKU_BUS_TRACE_LIMIT");
    if (bustrace_limit_env && bustrace_limit_env[0])
      bustrace_limit = strtoul(bustrace_limit_env, NULL, 0);
  }
  const char* cpm_disk_trace_path = getenv("JUKU_CPM_DISK_TRACE");
  if (cpm_disk_trace_path && cpm_disk_trace_path[0]) {
    cpm_disk_trace_fp = fopen(cpm_disk_trace_path, "w");
    if (!cpm_disk_trace_fp) {
      fprintf(stderr, "JUKU_CPM_DISK_TRACE=%s could not be opened for writing\n",
              cpm_disk_trace_path);
      return 2;
    }
    fputs("sequence operation drive track sector dma cycles\n",
          cpm_disk_trace_fp);
  }
  const char* cart_path = getenv("JUKU_CART");
  ctx->timing_log = getenv("JUKU_TRACE_TIMING") && getenv("JUKU_TRACE_TIMING")[0] &&
               strcmp(getenv("JUKU_TRACE_TIMING"), "0") != 0;
  ctx->io_trace = getenv("JUKU_TRACE_IO") && getenv("JUKU_TRACE_IO")[0] &&
               strcmp(getenv("JUKU_TRACE_IO"), "0") != 0;
  const char* bank_trace_env = getenv("JUKU_TRACE_BANK");
  if (bank_trace_env && bank_trace_env[0])
    ctx->bank_trace = strcmp(bank_trace_env, "0") != 0;
  const char* watch_address_env = getenv("JUKU_WATCH_ADDRESS");
  if (watch_address_env && watch_address_env[0]) {
    char* endptr = NULL;
    ctx->watch_address = (int)strtoul(watch_address_env, &endptr, 0);
    ctx->watch_address_end = ctx->watch_address;
    if (endptr && *endptr == '-')
      ctx->watch_address_end = (int)strtoul(endptr + 1, NULL, 0);
  }
  const char* usart_pty = getenv("JUKU_USART_PTY");
  const char* usart_fault = getenv("JUKU_USART_FAULT");
  const char* usart_transfer_cycles = getenv("JUKU_USART_TRANSFER_CYCLES");
  const char* usart_byte_cycles = getenv("JUKU_USART_BYTE_CYCLES");
  const char* usart_pit_clock_env = getenv("JUKU_USART_PIT_CLOCK");
  const char* usart_pit_cpu_hz_env = getenv("JUKU_USART_PIT_CPU_HZ");
  const char* usart_host_sync_env = getenv("JUKU_USART_HOST_SYNC_MS");
  const char* ram_fault = getenv("JUKU_RAM_FAULT");
  const char* rom_consecutive_a12_low_env =
      getenv("JUKU_ROM_CONSECUTIVE_A12_LOW");
  const char* cpu_a12_increment_fault_env =
      getenv("JUKU_CPU_A12_INCREMENT_FAULT");
  const char* cpu_a12_increment_fault_arm_pc_env =
      getenv("JUKU_CPU_A12_INCREMENT_FAULT_ARM_PC");
  const char* cpu_a12_increment_fault_disarm_pc_env =
      getenv("JUKU_CPU_A12_INCREMENT_FAULT_DISARM_PC");
  const char* cpu_a12_increment_fault_arm_bank_mode_env =
      getenv("JUKU_CPU_A12_INCREMENT_FAULT_ARM_BANK_MODE");
  const char* exec_byte_fault = getenv("JUKU_EXEC_BYTE_FAULT");
  const char* ram_drop_write = getenv("JUKU_RAM_DROP_WRITE");
  const char* ram_alias = getenv("JUKU_RAM_ALIAS");
  const char* dram_retention = getenv("JUKU_DRAM_RETENTION_CYCLES");
  const char* dram_retention_arm_pc_env =
      getenv("JUKU_DRAM_RETENTION_ARM_PC");
  const char* pic_fault = getenv("JUKU_PIC_FAULT");
  const char* ppi_fault = getenv("JUKU_PPI_FAULT");
  const char* pit_fault = getenv("JUKU_PIT_FAULT");
  if (exec_byte_fault && exec_byte_fault[0]) {
    unsigned address, value;
    char trailing;
    if (sscanf(exec_byte_fault, "%x:%x%c", &address, &value, &trailing) != 2 ||
        address > 0xFFFF || value > 0xFF) {
      fprintf(stderr,
              "invalid JUKU_EXEC_BYTE_FAULT=%s (expected ADDR:VALUE)\n",
              exec_byte_fault);
      return 2;
    }
    ctx->exec_byte_fault_enabled = 1;
    ctx->exec_byte_fault_addr = (uint16_t)address;
    ctx->exec_byte_fault_value = (uint8_t)value;
    fprintf(stderr, "[EXEC] byte fault address=0x%04X value=0x%02X\n",
            ctx->exec_byte_fault_addr, ctx->exec_byte_fault_value);
  }
  ctx->rom_consecutive_a12_low =
      rom_consecutive_a12_low_env && rom_consecutive_a12_low_env[0] &&
      strcmp(rom_consecutive_a12_low_env, "0") != 0;
  if (ctx->rom_consecutive_a12_low)
    fprintf(stderr, "[ROM] consecutive-read A12-low fault enabled\n");
  ctx->cpu_a12_increment_fault =
      cpu_a12_increment_fault_env && cpu_a12_increment_fault_env[0] &&
      strcmp(cpu_a12_increment_fault_env, "0") != 0;
  if (ctx->cpu_a12_increment_fault)
    fprintf(stderr, "[CPU] A12 increment-retention fault enabled\n");
  if (cpu_a12_increment_fault_arm_pc_env &&
      cpu_a12_increment_fault_arm_pc_env[0]) {
    char* end = NULL;
    unsigned long value = strtoul(
        cpu_a12_increment_fault_arm_pc_env, &end, 0);
    if (!end || *end || value > 0xFFFF) {
      fprintf(stderr,
              "invalid JUKU_CPU_A12_INCREMENT_FAULT_ARM_PC=%s\n",
              cpu_a12_increment_fault_arm_pc_env);
      return 2;
    }
    ctx->cpu_a12_increment_fault_arm_enabled = 1;
    ctx->cpu_a12_increment_fault_arm_pc = (uint16_t)value;
    ctx->cpu_a12_increment_fault = 0;
    fprintf(stderr, "[CPU] A12 increment fault will arm at pc=0x%04X\n",
            ctx->cpu_a12_increment_fault_arm_pc);
  }
  if (cpu_a12_increment_fault_disarm_pc_env &&
      cpu_a12_increment_fault_disarm_pc_env[0]) {
    char* end = NULL;
    unsigned long value = strtoul(
        cpu_a12_increment_fault_disarm_pc_env, &end, 0);
    if (!end || *end || value > 0xFFFF) {
      fprintf(stderr,
              "invalid JUKU_CPU_A12_INCREMENT_FAULT_DISARM_PC=%s\n",
              cpu_a12_increment_fault_disarm_pc_env);
      return 2;
    }
    if (!ctx->cpu_a12_increment_fault_arm_enabled) {
      fprintf(stderr,
              "JUKU_CPU_A12_INCREMENT_FAULT_DISARM_PC requires ARM_PC\n");
      return 2;
    }
    ctx->cpu_a12_increment_fault_disarm_enabled = 1;
    ctx->cpu_a12_increment_fault_disarm_pc = (uint16_t)value;
    fprintf(stderr, "[CPU] A12 increment fault will disarm at pc=0x%04X\n",
            ctx->cpu_a12_increment_fault_disarm_pc);
  }
  if (cpu_a12_increment_fault_arm_bank_mode_env &&
      cpu_a12_increment_fault_arm_bank_mode_env[0]) {
    char* end = NULL;
    unsigned long value = strtoul(
        cpu_a12_increment_fault_arm_bank_mode_env, &end, 0);
    if (!end || *end || value > 3 ||
        !ctx->cpu_a12_increment_fault_arm_enabled) {
      fprintf(stderr,
              "invalid JUKU_CPU_A12_INCREMENT_FAULT_ARM_BANK_MODE=%s\n",
              cpu_a12_increment_fault_arm_bank_mode_env);
      return 2;
    }
    ctx->cpu_a12_increment_fault_arm_bank_mode = (int)value;
    fprintf(stderr, "[CPU] A12 increment fault arm requires bank mode %d\n",
            ctx->cpu_a12_increment_fault_arm_bank_mode);
  }
  if (usart_transfer_cycles && usart_transfer_cycles[0]) {
    ctx->usart.transfer_cycles = strtoul(usart_transfer_cycles, 0, 0);
    if (!ctx->usart.transfer_cycles) ctx->usart.transfer_cycles = 1;
  }
  if (usart_byte_cycles && usart_byte_cycles[0]) {
    ctx->usart.byte_cycles = strtoul(usart_byte_cycles, 0, 0);
    if (!ctx->usart.byte_cycles) ctx->usart.byte_cycles = 1;
  }
  ctx->usart_pit_clock = env_enabled(usart_pit_clock_env);
  if (usart_pit_cpu_hz_env && usart_pit_cpu_hz_env[0]) {
    char* end = NULL;
    errno = 0;
    ctx->usart_pit_cpu_hz = strtoul(usart_pit_cpu_hz_env, &end, 0);
    if (errno || !end || *end || !ctx->usart_pit_cpu_hz) {
      fprintf(stderr, "invalid JUKU_USART_PIT_CPU_HZ=%s\n",
              usart_pit_cpu_hz_env);
      return 2;
    }
  }
  if (usart_host_sync_env && usart_host_sync_env[0]) {
    char* end = NULL;
    errno = 0;
    unsigned long value = strtoul(usart_host_sync_env, &end, 0);
    if (errno || !end || *end || !value || value > 60000UL) {
      fprintf(stderr,
              "invalid JUKU_USART_HOST_SYNC_MS=%s (expected 1..60000)\n",
              usart_host_sync_env);
      return 2;
    }
    ctx->usart_host_sync_ms = (int)value;
    fprintf(stderr, "[USART] native-host synchronization=%d ms\n",
            ctx->usart_host_sync_ms);
  }
  if (usart_fault && usart_fault[0]) {
    if (strcmp(usart_fault, "tx_stuck") == 0) {
      ctx->usart.fault_tx_stuck_permanent = 1;
    } else if (strncmp(usart_fault, "tx_stuck_once:", 14) == 0) {
      unsigned value;
      char trailing;
      if (sscanf(usart_fault, "tx_stuck_once:%x%c", &value, &trailing) != 1 ||
          value > 0xFF) {
        fprintf(stderr,
                "unknown JUKU_USART_FAULT=%s "
                "(expected tx_stuck or tx_stuck_once:BYTE)\n",
                usart_fault);
        return 2;
      }
      ctx->usart.fault_tx_stuck_once_enabled = 1;
      ctx->usart.fault_tx_stuck_once_value = (uint8_t)value;
    } else if (strncmp(usart_fault, "tx_not_ready_once_after:", 24) == 0) {
      unsigned long count;
      char trailing;
      if (sscanf(usart_fault, "tx_not_ready_once_after:%lu%c", &count, &trailing) != 1) {
        fprintf(stderr,
                "unknown JUKU_USART_FAULT=%s (expected tx_stuck, "
                "tx_stuck_once:BYTE, or tx_not_ready_once_after:COUNT)\n",
                usart_fault);
        return 2;
      }
      ctx->usart.fault_tx_not_ready_once_after_enabled = 1;
      ctx->usart.fault_tx_not_ready_once_after = count;
    } else if (strncmp(usart_fault, "rx_irq_delay_once_after:", 24) == 0) {
      unsigned long count, delay;
      char trailing;
      if (sscanf(usart_fault, "rx_irq_delay_once_after:%lu:%lu%c",
                 &count, &delay, &trailing) != 2 || !delay) {
        fprintf(stderr,
                "unknown JUKU_USART_FAULT=%s (expected "
                "rx_irq_delay_once_after:COUNT:CYCLES)\n",
                usart_fault);
        return 2;
      }
      ctx->usart.fault_rx_irq_delay_once_enabled = 1;
      ctx->usart.fault_rx_irq_delay_once_after = count;
      ctx->usart.fault_rx_irq_delay_cycles = delay;
    } else {
      unsigned long count;
      char trailing;
      if (sscanf(usart_fault, "tx_empty_low_after:%lu%c", &count, &trailing) != 1) {
        fprintf(stderr,
                "unknown JUKU_USART_FAULT=%s (expected tx_stuck, "
                "tx_stuck_once:BYTE, tx_not_ready_once_after:COUNT, "
                "rx_irq_delay_once_after:COUNT:CYCLES, or "
                "tx_empty_low_after:COUNT)\n",
                usart_fault);
        return 2;
      }
      ctx->usart.fault_tx_empty_low_after_enabled = 1;
      ctx->usart.fault_tx_empty_low_after = count;
    }
  }
  if (pic_fault && pic_fault[0]) {
    unsigned stuck_low, stuck_high;
    char trailing;
    if (sscanf(pic_fault, "%x:%x%c", &stuck_low, &stuck_high, &trailing) != 2 ||
        stuck_low > 0xFF || stuck_high > 0xFF || (stuck_low & stuck_high)) {
      fprintf(stderr,
              "invalid JUKU_PIC_FAULT=%s (expected STUCK_LOW:STUCK_HIGH)\n",
              pic_fault);
      return 2;
    }
    ctx->pic_fault_enabled = 1;
    ctx->pic_fault_stuck_low = (uint8_t)stuck_low;
    ctx->pic_fault_stuck_high = (uint8_t)stuck_high;
    fprintf(stderr, "[PIC] IMR fault stuck-low=0x%02X stuck-high=0x%02X\n",
            ctx->pic_fault_stuck_low, ctx->pic_fault_stuck_high);
  }
  if (ppi_fault && ppi_fault[0]) {
    unsigned port, stuck_low, stuck_high;
    char trailing;
    if (sscanf(ppi_fault, "%x:%x:%x%c", &port, &stuck_low, &stuck_high,
               &trailing) != 3 ||
        port < 0x0C || port > 0x0E || stuck_low > 0xFF ||
        stuck_high > 0xFF || (stuck_low & stuck_high)) {
      fprintf(stderr,
              "invalid JUKU_PPI_FAULT=%s "
              "(expected PORT:STUCK_LOW:STUCK_HIGH, PORT=0C..0E)\n",
              ppi_fault);
      return 2;
    }
    ctx->ppi_fault_enabled = 1;
    ctx->ppi_fault_port = (uint8_t)port;
    ctx->ppi_fault_stuck_low = (uint8_t)stuck_low;
    ctx->ppi_fault_stuck_high = (uint8_t)stuck_high;
    fprintf(stderr,
            "[PPI] D27 port 0x%02X fault stuck-low=0x%02X stuck-high=0x%02X\n",
            ctx->ppi_fault_port, ctx->ppi_fault_stuck_low, ctx->ppi_fault_stuck_high);
  }
  if (pit_fault && pit_fault[0]) {
    unsigned port, stuck_low, stuck_high;
    char trailing;
    if (sscanf(pit_fault, "%x:%x:%x%c", &port, &stuck_low, &stuck_high,
               &trailing) != 3 || port < 0x10 || port > 0x1A ||
        (port & 3) == 3 || stuck_low > 0xFF || stuck_high > 0xFF ||
        (stuck_low & stuck_high)) {
      fprintf(stderr,
              "invalid JUKU_PIT_FAULT=%s "
              "(expected PORT:STUCK_LOW:STUCK_HIGH, "
              "PORT=10..12/14..16/18..1A)\n",
              pit_fault);
      return 2;
    }
    ctx->pit_fault_enabled = 1;
    ctx->pit_fault_port = (uint8_t)port;
    ctx->pit_fault_stuck_low = (uint8_t)stuck_low;
    ctx->pit_fault_stuck_high = (uint8_t)stuck_high;
    fprintf(stderr,
            "[PIT] port 0x%02X fault stuck-low=0x%02X stuck-high=0x%02X\n",
            ctx->pit_fault_port, ctx->pit_fault_stuck_low, ctx->pit_fault_stuck_high);
  }
  if (ram_fault && ram_fault[0]) {
    unsigned address, stuck_low, stuck_high;
    char trailing;
    int parsed;
    if (ram_fault[0] == '*' && ram_fault[1] == ':') {
      parsed = sscanf(ram_fault + 2, "%x:%x%c", &stuck_low, &stuck_high,
                      &trailing);
      address = 0;
      ctx->ram_fault_all = 1;
    } else {
      parsed = sscanf(ram_fault, "%x:%x:%x%c", &address, &stuck_low,
                      &stuck_high, &trailing);
    }
    if (parsed != (ctx->ram_fault_all ? 2 : 3) || address > 0xFFFF ||
        stuck_low > 0xFF || stuck_high > 0xFF ||
        (stuck_low & stuck_high)) {
      fprintf(stderr,
              "invalid JUKU_RAM_FAULT=%s "
              "(expected ADDR:STUCK_LOW:STUCK_HIGH or *:STUCK_LOW:STUCK_HIGH)\n",
              ram_fault);
      return 2;
    }
    ctx->ram_fault_enabled = 1;
    ctx->ram_fault_addr = (uint16_t)address;
    ctx->ram_fault_stuck_low = (uint8_t)stuck_low;
    ctx->ram_fault_stuck_high = (uint8_t)stuck_high;
    if (ctx->ram_fault_all)
      fprintf(stderr, "[RAM] global fault stuck-low=0x%02X stuck-high=0x%02X\n",
              ctx->ram_fault_stuck_low, ctx->ram_fault_stuck_high);
    else
      fprintf(stderr,
              "[RAM] fault address=0x%04X stuck-low=0x%02X stuck-high=0x%02X\n",
              ctx->ram_fault_addr, ctx->ram_fault_stuck_low, ctx->ram_fault_stuck_high);
  }
  if (ram_drop_write && ram_drop_write[0]) {
    unsigned address, value, count;
    char trailing;
    if (sscanf(ram_drop_write, "%x:%x:%u%c", &address, &value, &count,
               &trailing) != 3 || address > 0xFFFF || value > 0xFF || !count) {
      fprintf(stderr,
              "invalid JUKU_RAM_DROP_WRITE=%s (expected ADDR:VALUE:COUNT)\n",
              ram_drop_write);
      return 2;
    }
    ctx->ram_drop_write_enabled = 1;
    ctx->ram_drop_write_addr = (uint16_t)address;
    ctx->ram_drop_write_value = (uint8_t)value;
    ctx->ram_drop_write_remaining = count;
    fprintf(stderr,
            "[RAM] will drop %u write(s) address=0x%04X value=0x%02X\n",
            count, ctx->ram_drop_write_addr, ctx->ram_drop_write_value);
  }
  if (ram_alias && ram_alias[0]) {
    unsigned page_a, page_b;
    char trailing;
    if (sscanf(ram_alias, "%x:%x%c", &page_a, &page_b, &trailing) != 2 ||
        page_a > 0xFF || page_b > 0xFF || page_a == page_b) {
      fprintf(stderr, "invalid JUKU_RAM_ALIAS=%s (expected distinct PAGE_A:PAGE_B)\n",
              ram_alias);
      return 2;
    }
    ctx->ram_alias_enabled = 1;
    ctx->ram_alias_page_a = (uint8_t)page_a;
    ctx->ram_alias_page_b = (uint8_t)page_b;
    fprintf(stderr, "[RAM] alias logical page 0x%02X -> physical page 0x%02X\n",
            ctx->ram_alias_page_b, ctx->ram_alias_page_a);
  }
  if (dram_retention && dram_retention[0]) {
    char* end = NULL;
    errno = 0;
    ctx->dram_retention_cycles = strtoul(dram_retention, &end, 0);
    if (errno || !end || *end || !ctx->dram_retention_cycles) {
      fprintf(stderr,
              "invalid JUKU_DRAM_RETENTION_CYCLES=%s (expected positive integer)\n",
              dram_retention);
      return 2;
    }
    fprintf(stderr, "[DRAM] retention limit=%lu cycles across 128 rows\n",
            ctx->dram_retention_cycles);
    if (dram_retention_arm_pc_env && dram_retention_arm_pc_env[0]) {
      unsigned address;
      char trailing;
      if (sscanf(dram_retention_arm_pc_env, "%x%c", &address, &trailing) != 1 ||
          address > 0xFFFF) {
        fprintf(stderr,
                "invalid JUKU_DRAM_RETENTION_ARM_PC=%s (expected address)\n",
                dram_retention_arm_pc_env);
        return 2;
      }
      ctx->dram_retention_arm_pc_enabled = 1;
      ctx->dram_retention_arm_pc = (uint16_t)address;
      ctx->dram_retention_armed = 0;
      fprintf(stderr, "[DRAM] retention waits for pc=0x%04X\n",
              ctx->dram_retention_arm_pc);
    }
  }
  if (env_enabled(usart_pty) && usart_open_transport(ctx, usart_pty) != 0) {
    fprintf(stderr, "JUKU_USART_PTY=%s could not be opened: %s\n", usart_pty, strerror(errno));
    return 2;
  }
  const char* fdc_bus_invert_env = getenv("JUKU_FDC_BUS_INVERT");
  ctx->fdc_bus_invert = fdc_bus_invert_env && fdc_bus_invert_env[0] &&
                   strcmp(fdc_bus_invert_env, "0") != 0;
  if (cart_path && cart_path[0]) {
    size_t cn = load_image(cart_path, ctx->cart, CART_SIZE, 0xFF);
    ctx->cart_enabled = 1;
    fprintf(stderr, "loaded %zu bytes of expansion cartridge from %s\n", cn, cart_path);
  } else {
    memset(ctx->cart, 0xFF, sizeof(ctx->cart));
  }
  const char* disk_path = getenv("JUKU_DISK");
  if (disk_path && disk_path[0]) {
    const char* writable_env = getenv("JUKU_DISK_WRITABLE");
    int disk_writable = writable_env && writable_env[0] && strcmp(writable_env, "0") != 0;
    int rc = disk_writable ? juk_disk_open_writable(&ctx->disk, disk_path)
                           : juk_disk_open(&ctx->disk, disk_path);
    if (rc != 0) {
      fprintf(stderr, "JUKU_DISK=%s could not be opened as a raw Juku disk image (rc=%d)\n", disk_path, rc);
      return 2;
    }
    const char* deleted_marks_path = getenv("JUKU_DISK_DELETED_MARKS");
    if (deleted_marks_path && deleted_marks_path[0]) {
      rc = juk_disk_attach_deleted_marks(&ctx->disk, deleted_marks_path);
      if (rc != 0) {
        fprintf(stderr, "JUKU_DISK_DELETED_MARKS=%s could not be attached (rc=%d)\n",
                deleted_marks_path, rc);
        juk_disk_close(&ctx->disk);
        return 2;
      }
    }
    juku_fdc_init(&ctx->fdc, &ctx->disk);
    ctx->fdc_enabled = 1;
    fprintf(stderr, "loaded JUKU disk image %s (%ld bytes, %d side%s, %s, FDC bus %s)\n",
            disk_path, ctx->disk.size, ctx->disk.heads, ctx->disk.heads == 1 ? "" : "s",
            disk_writable ? "writable" : "read-only",
            ctx->fdc_bus_invert ? "inverting" : "non-inverting");
    if (deleted_marks_path && deleted_marks_path[0])
      fprintf(stderr, "loaded JUKU deleted-record metadata %s\n", deleted_marks_path);
  }

  size_t n = load_image(rom_path, ctx->rom, ROM_SIZE, 0x00);
  fprintf(stderr, "loaded %zu bytes of ROM from %s\n", n, rom_path);

  // ekta43.bin (homebrew AT-kbd mod) has a STALE block-1 checksum: bytes
  // 0x000B..0x07FF sum to 0x57 but the stored checksum at 0x000A is 0xF2, so the
  // ROM self-test fails and retries forever. Patch the stored byte to boot.
  if (ctx->rom[0x0A] == 0xF2 && (sum_block(ctx->rom) == 0x57)) {
    ctx->rom[0x0A] = 0x57;
    fprintf(stderr, "[PATCH] ekta43 block-1 checksum 0x000A: 0xF2 -> 0x57 (stale homebrew checksum)\n");
  }

  ctx->cpu.fault_a12_increment_high_loss = ctx->cpu_a12_increment_fault;
  ctx->cpu.pc = 0x0000;

  unsigned long last_write_total = 0, writes_total, idle_cyc = 0;
  static uint32_t pchist[MEM_SIZE];

  // Optional interactive console (JUKU_CONSOLE_PTY).
  const char* console_env = getenv("JUKU_CONSOLE_PTY");
  if (console_env && console_env[0]) {
    console_fd = open_serial_endpoint(console_env, "TERM");
    if (console_fd < 0) {
      fprintf(stderr, "JUKU_CONSOLE_PTY=%s could not be opened\n", console_env);
      return 2;
    }
    const char* out_pc = getenv("JUKU_CONSOLE_OUT_PC");
    const char* out_register = getenv("JUKU_CONSOLE_OUT_REGISTER");
    const char* out_disable = getenv("JUKU_CONSOLE_OUT_DISABLE");
    const char* in_pc = getenv("JUKU_CONSOLE_IN_PC");
    if (out_disable && out_disable[0] && strcmp(out_disable, "0") != 0)
      console_out_enabled = 0;
    if (out_pc && out_pc[0]) console_out_pc = (uint16_t)strtoul(out_pc, NULL, 0);
    if (out_register && out_register[0]) {
      if (strcmp(out_register, "C") == 0 || strcmp(out_register, "c") == 0)
        console_out_register_c = 1;
      else if (strcmp(out_register, "A") != 0 && strcmp(out_register, "a") != 0) {
        fprintf(stderr, "invalid JUKU_CONSOLE_OUT_REGISTER=%s (expected A or C)\n",
                out_register);
        return 2;
      }
    }
    if (in_pc && in_pc[0]) console_in_pc = (uint16_t)strtoul(in_pc, NULL, 0);
    (void)console_in_pc;
    ctx->kbd_enabled = 1;
    // Scripted JUKU_KEYS and an operator's typing share one queue: the script
    // plays first, then whatever is typed is appended behind it. A run with no
    // script drops the "wait for the banner" gate, since an operator chooses
    // when to type.
    ctx->console_queue[0] = 0;
    ctx->console_len = 0;
    if (ctx->kbd_str && ctx->kbd_str[0]) {
      for (const char* c = ctx->kbd_str; *c && ctx->console_len + 1 < CONSOLE_QUEUE; c++)
        ctx->console_queue[ctx->console_len++] = *c;
      ctx->console_queue[ctx->console_len] = 0;
    } else {
      ctx->kbd_start_vram = 0;
    }
    ctx->kbd_str = ctx->console_queue;
    ctx->kbd_pos = 0;
    if (console_out_enabled)
      fprintf(stderr, "[TERM] console attached; output hook=%04X register=%c\n",
              console_out_pc, console_out_register_c ? 'C' : 'A');
    else
      fprintf(stderr, "[TERM] keyboard attached; output hook=disabled\n");
  }

  // Optional real-time pacing (JUKU_REALTIME_HZ). Sleeps whenever simulated
  // time has run ahead of wall-clock time, so a session takes as long as it
  // would on the machine. Checked on a coarse cycle interval and only slept
  // when the lead exceeds one slice, which keeps the syscall rate low; the
  // pacer never speeds a slow host up, so it cannot mask a lagging model.
  const char* realtime_env = getenv("JUKU_REALTIME_HZ");
  unsigned long realtime_hz = 0;
  if (realtime_env && realtime_env[0]) {
    char* endptr = NULL;
    realtime_hz = strtoul(realtime_env, &endptr, 0);
    if (endptr == realtime_env || (endptr && *endptr) || realtime_hz == 0) {
      fprintf(stderr,
              "invalid JUKU_REALTIME_HZ=%s (expected a positive cycle rate)\n",
              realtime_env);
      return 2;
    }
    if (realtime_hz == 1) realtime_hz = 2000000UL;   // nominal Juku clock
    fprintf(stderr, "[SPEED] pacing to %lu cycles/second\n", realtime_hz);
  }
  const unsigned long realtime_slice = 2000;   // ~1 ms of machine time at 2 MHz
  unsigned long realtime_next = realtime_slice;
  struct timespec realtime_start;
  if (realtime_hz) clock_gettime(CLOCK_MONOTONIC, &realtime_start);

  int chk_entry_logs = 0;
  int chk_compare_logs = 0;
  const int pc_history_enabled = env_enabled(getenv("JUKU_PC_HISTORY"));
  const int tpa_stack_trace_enabled =
      env_enabled(getenv("JUKU_TPA_STACK_TRACE"));
  uint16_t pc_history[256] = {0};
  unsigned pc_history_pos = 0;
  while (ctx->cpu.cyc < max_cyc && (!ctx->cpu.halted || ctx->frame_cyc) &&
         !(ctx->g_vw_limit && ctx->g_vw >= ctx->g_vw_limit) &&
         !(checkpoint_cyc && ctx->cpu.cyc >= checkpoint_cyc) &&
         !(stop_pc_enabled && ctx->usart.rx_bytes >= stop_pc_after_usart_rx &&
           ctx->cpu.pc == stop_pc) &&
         !(stop_keys_done && ctx->kbd_str && !ctx->kbd_str[ctx->kbd_pos]) &&
         !stop_prompt_hit &&
         !terminate_requested &&
         !(ctx->stop_fdc_data_reads && ctx->fdc_data_reads >= ctx->stop_fdc_data_reads)) {
    if ((unsigned long)checkpoint_requests > ctx->checkpoint_generation) {
      dump_checkpoint(ctx, getenv("JUKU_CHECKPOINT_PREFIX"), &ctx->cpu);
    }
    if ((unsigned long)tpa_measurement_requests >
        ctx->tpa_measurement_generation) {
      ctx->tpa_measurement_generation =
          (unsigned long)tpa_measurement_requests;
      ctx->tpa_measurement_controlled = 1;
      ctx->tpa_measurement_armed = 1;
      ctx->tpa_measurement_frozen = 0;
      ctx->tpa_program_seen = 0;
      ctx->tpa_program_in_bdos = 0;
      ctx->tpa_program_bdos_tail_call = 0;
    }
    if (ctx->cpu_a12_increment_fault_arm_enabled &&
        !ctx->cpu_a12_increment_fault_arm_fired &&
        (ctx->cpu_a12_increment_fault_arm_bank_mode < 0 ||
         ctx->mode == ctx->cpu_a12_increment_fault_arm_bank_mode) &&
        ctx->cpu.pc == ctx->cpu_a12_increment_fault_arm_pc) {
      ctx->cpu_a12_increment_fault_arm_fired = 1;
      ctx->cpu_a12_increment_fault = 1;
      ctx->cpu.fault_a12_increment_high_loss = 1;
      fprintf(stderr, "[CPU] A12 increment fault armed at pc=%04X cyc=%lu\n",
              ctx->cpu.pc, ctx->cpu.cyc);
    }
    if (ctx->cpu_a12_increment_fault_disarm_enabled &&
        ctx->cpu_a12_increment_fault_arm_fired &&
        !ctx->cpu_a12_increment_fault_disarm_fired &&
        ctx->cpu.pc == ctx->cpu_a12_increment_fault_disarm_pc) {
      ctx->cpu_a12_increment_fault_disarm_fired = 1;
      ctx->cpu_a12_increment_fault = 0;
      ctx->cpu.fault_a12_increment_high_loss = 0;
      fprintf(stderr,
              "[CPU] A12 increment fault disarmed at pc=%04X cyc=%lu\n",
              ctx->cpu.pc, ctx->cpu.cyc);
    }
    if (reset_after_rx && !reset_after_rx_fired &&
        ctx->usart.rx_bytes >= reset_after_rx) {
      reset_after_rx_fired = 1;
      fprintf(stderr,
              "[RESET] one-shot board reset after USART byte=%lu cyc=%lu\n",
              ctx->usart.rx_bytes, ctx->cpu.cyc);
      ctx->cpu.pc = 0;
      ctx->cpu.iff = 0;
      ctx->cpu.halted = 0;
      juku_set_mode(ctx, 0);
      ctx->video_stride = VID_DEFAULT_STRIDE;
      ctx->video_lines = VID_DEFAULT_LINES;
      ctx->video_modx_sequence = 0;
      ctx->video_stock_sequence = 0;
      ctx->video_64_sequence = 0;
      ctx->video_modx_mode = 0;
      ctx->video_console_mode = 0;
      juku_usart_reset(ctx);
      ctx->kbd_pos = 0;
      ctx->kbd_phase = 0;
    }
    if (ctx->dram_retention_arm_pc_enabled && !ctx->dram_retention_armed &&
        ctx->cpu.pc == ctx->dram_retention_arm_pc) {
      ctx->dram_retention_armed = 1;
      for (unsigned row = 0; row < 128; row++)
        ctx->dram_last_refresh[row] = ctx->cpu.cyc;
      memset(ctx->dram_coverage_seen, 0, sizeof(ctx->dram_coverage_seen));
      ctx->dram_coverage_count = 0;
      ctx->dram_coverage_start = ctx->cpu.cyc;
      ctx->dram_full_coverage_reported = 0;
      fprintf(stderr, "[DRAM] retention armed at pc=0x%04X cyc=%lu\n",
              ctx->cpu.pc, ctx->cpu.cyc);
    }
    if (rom_exec_reset_at && ctx->mode == 0 && ctx->cpu.pc >= rom_exec_reset_at &&
        ctx->cpu.pc < 0x4000) {
      rom_exec_resets++;
      if (rom_exec_resets <= 32)
        fprintf(stderr,
                "[EXEC] reset #%lu at ROM pc=%04X boundary=%04lX cyc=%lu\n",
                rom_exec_resets, ctx->cpu.pc, rom_exec_reset_at, ctx->cpu.cyc);
      ctx->cpu.pc = 0;
      ctx->cpu.iff = 0;
      ctx->cpu.halted = 0;
      juku_set_mode(ctx, 0);
      ctx->video_stride = VID_DEFAULT_STRIDE;
      ctx->video_lines = VID_DEFAULT_LINES;
      ctx->video_modx_sequence = 0;
      ctx->video_stock_sequence = 0;
      ctx->video_64_sequence = 0;
      ctx->video_modx_mode = 0;
      ctx->video_console_mode = 0;
    }
    if (ctx->kbd_pc_trigger_enabled && !ctx->kbd_pc_trigger_fired &&
        (!ctx->kbd_pc_trigger_gate_enabled ||
         juku_peek_byte(ctx, ctx->kbd_pc_trigger_gate_address) ==
             ctx->kbd_pc_trigger_gate_value) &&
        ctx->cpu.pc == ctx->kbd_pc_trigger_pc) {
      ctx->kbd_pc_trigger_fired = 1;
      ctx->kbd_pc_trigger_active = 1;
      ctx->kbd_phase = 0;
      fprintf(stderr,
              "[KBD] triggered char=%02X at pc=%04X cyc=%lu\n",
              (unsigned char)ctx->kbd_pc_trigger_char, ctx->cpu.pc, ctx->cpu.cyc);
    }
    pchist[ctx->cpu.pc]++;
    if (pc_history_enabled) {
      pc_history[pc_history_pos & 255] = ctx->cpu.pc;
      pc_history_pos++;
    }
    if (ctx->cpu.pc == 0x03E0 && chk_entry_logs++ < 12)    // checksum entry: HL=ptr, DE=count
      fprintf(stderr, "[CHK] entry HL=%04X DE=%04X mode=%d\n",
              (ctx->cpu.h<<8)|ctx->cpu.l, (ctx->cpu.d<<8)|ctx->cpu.e, ctx->mode);
    if (ctx->cpu.pc == 0x03E6 && chk_compare_logs++ < 12)   // compare: A=stored, B=computed
      fprintf(stderr, "[CHK] cmp computed=%02X stored=%02X %s\n",
              ctx->cpu.b, ctx->cpu.a, ctx->cpu.b==ctx->cpu.a ? "OK" : "**MISMATCH**");
    if (console_fd >= 0) {
      // The firmware's console character is in A when it enters the ROM's
      // WRCHR vector; mirror it to the terminal verbatim. The firmware sends
      // its own CR/LF pairs, so synthesising a newline here would double every
      // line break. The same routine runs at its banked address in modes 1/2
      // and at its ROM-file address in mode 0, so accept either.
      if (console_out_enabled && (ctx->cpu.pc == console_out_pc ||
          (console_out_pc >= 0xC000 &&
           ctx->cpu.pc == (uint16_t)(console_out_pc - 0xC000)))) {
        char out = (char)(console_out_register_c ? ctx->cpu.c : ctx->cpu.a);
        ssize_t ignored = write(console_fd, &out, 1);
        (void)ignored;
      }
      if (ctx->cpu.cyc >= console_poll_at) {
        console_poll(ctx);
        console_poll_at = ctx->cpu.cyc + 0x400;
      }
    }
    if (cpm_disk_trace_fp && (ctx->cpu.pc == 0xC027 || ctx->cpu.pc == 0xC02A)) {
      uint8_t drive = juku_peek_byte(ctx, 0xC93A);
      uint16_t track = juku_peek_word(ctx, 0xC93B);
      uint8_t sector = juku_peek_byte(ctx, 0xC93D);
      uint16_t dma = juku_peek_word(ctx, 0xC94E);
      fprintf(cpm_disk_trace_fp, "%lu %c %u %u %u %04X %lu\n",
              ++cpm_disk_trace_sequence,
              ctx->cpu.pc == 0xC027 ? 'R' : 'W', drive, track, sector, dma,
              ctx->cpu.cyc);
    }
    if (realtime_hz && ctx->cpu.cyc >= realtime_next) {
      realtime_next = ctx->cpu.cyc + realtime_slice;
      struct timespec now;
      clock_gettime(CLOCK_MONOTONIC, &now);
      double elapsed = (double)(now.tv_sec - realtime_start.tv_sec) +
                       (double)(now.tv_nsec - realtime_start.tv_nsec) / 1e9;
      double due = (double)ctx->cpu.cyc / (double)realtime_hz;
      double lead = due - elapsed;
      if (lead > 0.0005) {                     // only sleep a worthwhile lead
        struct timespec nap;
        nap.tv_sec = (time_t)lead;
        nap.tv_nsec = (long)((lead - (double)nap.tv_sec) * 1e9);
        nanosleep(&nap, NULL);
      }
    }
    int instruction_will_execute = !ctx->cpu.halted ||
      (ctx->cpu.interrupt_pending && ctx->cpu.iff && ctx->cpu.interrupt_delay == 0);
    uint16_t instruction_sp = ctx->cpu.sp;
    juku_step_cpu(ctx);
    /* A transient can tail-call BDOS with JMP 0005h while its caller's return
     * address is outside the TPA (normally page-zero warm boot). The existing
     * resume detector below runs only for instructions fetched in the TPA, so
     * that legitimate exit used to leave a controlled stack measurement
     * permanently active. Observe the first instruction at the recorded
     * non-TPA return address and freeze the completed transient explicitly. */
    if (instruction_will_execute && !ctx->cpu.last_opcode_was_interrupt &&
        ctx->tpa_program_seen && ctx->tpa_program_in_bdos &&
        (ctx->cpu.last_opcode_pc < 0x0100 || ctx->cpu.last_opcode_pc > 0x99FF) &&
        ctx->cpu.last_opcode_pc == ctx->tpa_program_bdos_return_pc) {
      int bdos_tail_call = ctx->tpa_program_bdos_tail_call;
      ctx->tpa_program_in_bdos = 0;
      ctx->tpa_program_bdos_tail_call = 0;
      if (bdos_tail_call && ctx->tpa_program_call_depth)
        ctx->tpa_program_call_depth--;
      ctx->tpa_program_seen = 0;
      if (ctx->tpa_measurement_controlled)
        ctx->tpa_measurement_frozen = 1;
      if (tpa_stack_trace_enabled)
        fprintf(stderr,
                "[TPA-STACK] non-TPA tail exit pc=%04X sp=%04X "
                "tail=%d depth=%u bytes=%u cyc=%lu\n",
                ctx->cpu.last_opcode_pc, instruction_sp, bdos_tail_call,
                ctx->tpa_program_call_depth, ctx->tpa_program_stack_bytes, ctx->cpu.cyc);
    }
    if (instruction_will_execute && !ctx->cpu.last_opcode_was_interrupt &&
        ctx->cpu.last_opcode_pc >= 0x0100 && ctx->cpu.last_opcode_pc <= 0x99FF) {
      uint8_t opcode = ctx->cpu.last_opcode;
      /* CP/M transients enter at 0100h. Startup code may establish one or
       * more private stack segments with LXI SP or SPHL. Track each segment
       * independently and preserve the largest observed depth; this handles
       * relocators such as SID as well as ordinary single-stack compilers.
       * Resident CCP/BDOS stack traffic remains excluded. */
      if (ctx->cpu.last_opcode_pc == 0x0100 && !ctx->tpa_program_in_bdos &&
          (!ctx->tpa_measurement_controlled || ctx->tpa_measurement_armed)) {
        ctx->tpa_program_starts++;
        ctx->tpa_program_entry_sp = instruction_sp;
        ctx->tpa_program_stack_anchor_sp = instruction_sp;
        ctx->tpa_program_stack_low_sp = instruction_sp;
        ctx->tpa_program_current_stack_anchor_sp = instruction_sp;
        ctx->tpa_program_segment_min_anchor_sp = instruction_sp;
        ctx->tpa_program_segment_max_anchor_sp = instruction_sp;
        ctx->tpa_program_stack_segments = 1;
        ctx->tpa_program_stack_bytes = 0;
        ctx->tpa_program_explicit_sp_writes = 0;
        ctx->tpa_program_call_depth = 0;
        ctx->tpa_program_bdos_return_pc = 0;
        ctx->tpa_program_in_bdos = 0;
        ctx->tpa_program_bdos_tail_call = 0;
        ctx->tpa_program_seen = 1;
        ctx->tpa_measurement_armed = 0;
        if (tpa_stack_trace_enabled)
          fprintf(stderr, "[TPA-STACK] entry sp=%04X cyc=%lu\n",
                  instruction_sp, ctx->cpu.cyc);
      }
      if (ctx->tpa_program_seen && ctx->tpa_program_in_bdos &&
          ctx->cpu.last_opcode_pc == ctx->tpa_program_bdos_return_pc) {
        int bdos_tail_call = ctx->tpa_program_bdos_tail_call;
        int top_level_tail_exit =
            bdos_tail_call && ctx->tpa_program_call_depth == 0;
        ctx->tpa_program_in_bdos = 0;
        ctx->tpa_program_bdos_tail_call = 0;
        /* JMP 0005h lets BDOS RET consume the return address of the
         * transient helper that made the tail call. Mirror that implicit
         * return in the semantic call depth. Without it, every such call
         * leaks a frame and the eventual top-level RET is missed. */
        if (bdos_tail_call && ctx->tpa_program_call_depth)
          ctx->tpa_program_call_depth--;
        if (top_level_tail_exit) {
          ctx->tpa_program_seen = 0;
          if (ctx->tpa_measurement_controlled)
            ctx->tpa_measurement_frozen = 1;
        }
        if (tpa_stack_trace_enabled)
          fprintf(stderr,
                  "[TPA-STACK] resume pc=%04X sp=%04X tail=%d exit=%d "
                  "depth=%u cyc=%lu\n",
                  ctx->cpu.last_opcode_pc, instruction_sp, bdos_tail_call,
                  top_level_tail_exit, ctx->tpa_program_call_depth, ctx->cpu.cyc);
      }
      if (ctx->tpa_program_seen && !ctx->tpa_program_in_bdos) {
        if (opcode == 0x31 || opcode == 0xF9) {
          int first_sp_write = ctx->tpa_program_explicit_sp_writes++ == 0;
          /* The first explicit write selects the program's private stack.
           * A later LXI SP is also an unambiguous new segment (notably SID's
           * post-relocation stack). Later SPHL instructions are counted but
           * not treated as anchors: historical tools also use SPHL to borrow
           * SP as a general 16-bit register. */
          if (first_sp_write || opcode == 0x31) {
            ctx->tpa_program_current_stack_anchor_sp = ctx->cpu.sp;
            ctx->tpa_program_stack_segments++;
            if (ctx->cpu.sp < ctx->tpa_program_segment_min_anchor_sp)
              ctx->tpa_program_segment_min_anchor_sp = ctx->cpu.sp;
            if (ctx->cpu.sp > ctx->tpa_program_segment_max_anchor_sp)
              ctx->tpa_program_segment_max_anchor_sp = ctx->cpu.sp;
            if (first_sp_write && ctx->tpa_program_stack_bytes == 0) {
              ctx->tpa_program_stack_anchor_sp = ctx->cpu.sp;
              ctx->tpa_program_stack_low_sp = ctx->cpu.sp;
            }
          }
          if (tpa_stack_trace_enabled)
            fprintf(stderr,
                    "[TPA-STACK] SP write pc=%04X opcode=%02X "
                    "sp=%04X writes=%u segments=%u cyc=%lu\n",
                    ctx->cpu.last_opcode_pc, opcode, ctx->cpu.sp,
                    ctx->tpa_program_explicit_sp_writes,
                    ctx->tpa_program_stack_segments, ctx->cpu.cyc);
        } else {
          unsigned depth =
              (unsigned)(ctx->tpa_program_current_stack_anchor_sp - ctx->cpu.sp);
          if (depth < 0x8000u && depth > ctx->tpa_program_stack_bytes) {
            ctx->tpa_program_stack_bytes = depth;
            ctx->tpa_program_stack_anchor_sp =
                ctx->tpa_program_current_stack_anchor_sp;
            ctx->tpa_program_stack_low_sp = ctx->cpu.sp;
          }
        }
      }
      if (ctx->tpa_program_seen && !ctx->tpa_program_in_bdos) {
        int bdos_system_reset =
            (opcode == 0xCD || opcode == 0xC3) && ctx->cpu.pc == 0x0005 &&
            ctx->cpu.c == 0;
        if (bdos_system_reset) {
          /* BDOS function 0 does not return. DRI's PL/M startup commonly
           * emits MVI C,0 / CALL 0005h, so following that resident excursion
           * would attribute the CCP/BDOS stack to the finished transient and
           * leave a command-scoped measurement permanently unfrozen. */
          ctx->tpa_program_seen = 0;
        } else if ((opcode == 0xCD || opcode == 0xC3) &&
                   ctx->cpu.pc == 0x0005) {
          ctx->tpa_program_bdos_tail_call = opcode == 0xC3;
          ctx->tpa_program_bdos_return_pc = opcode == 0xCD
              ? (uint16_t)(ctx->cpu.last_opcode_pc + 3)
              : juku_peek_word(ctx, instruction_sp);
          ctx->tpa_program_in_bdos = 1;
          if (tpa_stack_trace_enabled)
            fprintf(stderr,
                    "[TPA-STACK] BDOS pc=%04X return=%04X tail=%d "
                    "sp=%04X cyc=%lu\n",
                    ctx->cpu.last_opcode_pc, ctx->tpa_program_bdos_return_pc,
                    ctx->tpa_program_bdos_tail_call, ctx->cpu.sp, ctx->cpu.cyc);
        }
        int conditional_call =
            opcode == 0xC4 || opcode == 0xCC || opcode == 0xD4 ||
            opcode == 0xDC || opcode == 0xE4 || opcode == 0xEC ||
            opcode == 0xF4 || opcode == 0xFC;
        int internal_call =
            (opcode == 0xCD ||
             (conditional_call &&
              ctx->cpu.pc != (uint16_t)(ctx->cpu.last_opcode_pc + 3))) &&
            ctx->cpu.pc >= 0x0100 && ctx->cpu.pc <= 0x99FF;
        int return_taken = opcode == 0xC9 || opcode == 0xE9 ||
            ((opcode == 0xC0 || opcode == 0xC8 || opcode == 0xD0 ||
              opcode == 0xD8 || opcode == 0xE0 || opcode == 0xE8 ||
              opcode == 0xF0 || opcode == 0xF8) &&
             ctx->cpu.pc != (uint16_t)(ctx->cpu.last_opcode_pc + 1));
        if (!ctx->tpa_program_seen) {
          /* A terminal BDOS function-0 call was recognized above. */
        } else if (ctx->tpa_program_in_bdos) {
          /* CALL 0005h returns to the recorded transient address; resident
           * BDOS stack traffic is deliberately outside this measurement. */
        } else if (internal_call) {
          ctx->tpa_program_call_depth++;
        } else if (return_taken) {
          if (ctx->tpa_program_call_depth)
            ctx->tpa_program_call_depth--;
          else
            ctx->tpa_program_seen = 0;
        } else if ((opcode & 0xC7) == 0xC7 || ctx->cpu.pc == 0x0000) {
          /* CP/M programs use RST 0 or a jump through page zero to exit. */
          ctx->tpa_program_seen = 0;
        }
        if (!ctx->tpa_program_seen && tpa_stack_trace_enabled)
          fprintf(stderr,
                  "[TPA-STACK] exit pc=%04X opcode=%02X target=%04X "
                  "depth=%u bytes=%u cyc=%lu\n",
                  ctx->cpu.last_opcode_pc, opcode, ctx->cpu.pc,
                  ctx->tpa_program_call_depth, ctx->tpa_program_stack_bytes, ctx->cpu.cyc);
        if (!ctx->tpa_program_seen && ctx->tpa_measurement_controlled)
          ctx->tpa_measurement_frozen = 1;
      }
      ctx->tpa_opcode_fetches++;
      if (opcode == 0xCB || opcode == 0xDD || opcode == 0xED ||
          opcode == 0xFD)
        ctx->tpa_z80_prefix_fetches++;
      if (opcode == 0x08 || opcode == 0x10 || opcode == 0x18 ||
          opcode == 0x20 || opcode == 0x28 || opcode == 0x30 ||
          opcode == 0x38 || opcode == 0xCB || opcode == 0xD9 ||
          opcode == 0xDD || opcode == 0xED || opcode == 0xFD)
        ctx->tpa_undocumented_opcode_fetches++;
    }
    juku_step_devices(ctx);
    if (!disable_settle && (ctx->cpu.cyc & 0xFFFFF) == 0) {
      writes_total = 0;
      for (int i = 0; i < 256; i++) writes_total += ctx->wpage[i];
      if (writes_total == last_write_total) {
        idle_cyc += 0x100000;
        if (idle_cyc > 4UL * 0x100000) {
          fprintf(stderr, "\n*** settled: no RAM writes ~4M cycles (idle at prompt?) ***\n");
          break;
        }
      } else { idle_cyc = 0; last_write_total = writes_total; }
    }
  }

  fprintf(stderr, "\nstopped pc=0x%04X cyc=%lu halted=%d iff=%d mode=%d switches=%lu\n",
          ctx->cpu.pc, ctx->cpu.cyc, ctx->cpu.halted, ctx->cpu.iff, ctx->mode, ctx->mode_switches);
  if (pc_history_enabled) {
    unsigned count = pc_history_pos < 256 ? pc_history_pos : 256;
    unsigned start = pc_history_pos - count;
    fprintf(stderr, "[EXEC] recent PCs:");
    for (unsigned i = 0; i < count; i++)
      fprintf(stderr, " %04X", pc_history[(start + i) & 255]);
    fputc('\n', stderr);
  }
  if (ctx->stop_fdc_data_reads && ctx->fdc_data_reads >= ctx->stop_fdc_data_reads)
    fprintf(stderr, "[FDC] stopped after %lu data reads at cyc=%lu pc=%04X g_vw=%lu\n",
            ctx->fdc_data_reads, ctx->cpu.cyc, ctx->cpu.pc, ctx->g_vw);
  if (stop_keys_done && ctx->kbd_str && !ctx->kbd_str[ctx->kbd_pos])
    fprintf(stderr, "[KBD] stopped after completing scripted input at cyc=%lu pc=%04X g_vw=%lu\n",
            ctx->cpu.cyc, ctx->cpu.pc, ctx->g_vw);
  if (stop_pc_enabled && ctx->usart.rx_bytes >= stop_pc_after_usart_rx &&
      ctx->cpu.pc == stop_pc)
    fprintf(stderr,
            "[EXEC] stopped before pc=%04lX after %lu USART receive bytes\n",
            stop_pc, ctx->usart.rx_bytes);
  if (stop_prompt_hit)
    fprintf(stderr, "[EXEC] stopped at A> prompt after %lu USART receive bytes\n",
            ctx->usart.rx_bytes);

  dump_checkpoint(ctx, getenv("JUKU_CHECKPOINT_PREFIX"), &ctx->cpu);
  capture_video_frame(ctx, ctx->cpu.cyc);

  printf("\n==== OUT ports ====\n");
  for (int p = 0; p < 256; p++)
    if (ctx->out_count[p]) printf("  0x%02X : %8lu  last=0x%02X\n", p, ctx->out_count[p], ctx->out_last[p]);
  printf("\n==== IN ports ====\n");
  for (int p = 0; p < 256; p++)
    if (ctx->in_count[p]) printf("  0x%02X : %8lu reads\n", p, ctx->in_count[p]);

  printf("\n==== hottest PCs ====\n");
  for (int top = 0; top < 10; top++) {
    uint32_t best = 0; int bi = -1;
    for (int i = 0; i < (int)MEM_SIZE; i++) if (pchist[i] > best) { best = pchist[i]; bi = i; }
    if (bi < 0 || !best) break;
    printf("  0x%04X : %u\n", bi, best); pchist[bi] = 0;
  }

  printf("\n==== RAM write density (pages >0) ====\n");
  for (int pg = 0; pg < 256; pg++)
    if (ctx->wpage[pg]) printf("  0x%02X00 : %8lu\n", pg, ctx->wpage[pg]);

  FILE* o = fopen("vram.bin", "wb");
  if (o) { fwrite(&ctx->ram[VRAM_BASE], 1, (size_t)ctx->video_stride * ctx->video_lines, o); fclose(o);
           printf("\nwrote vram.bin (%u bytes, %ux%u @ 0x%04X)\n",
                  ctx->video_stride * ctx->video_lines, ctx->video_stride * 8,
                  ctx->video_lines, VRAM_BASE); }
  if (ctx->fdc_enabled) juk_disk_close(&ctx->disk);
  if (usart_fd >= 0) close(usart_fd);
  if (rdtrace_fp) fclose(rdtrace_fp);
  if (bustrace_fp) fclose(bustrace_fp);
  if (cpm_disk_trace_fp) fclose(cpm_disk_trace_fp);
  if (video_capture_fp) fclose(video_capture_fp);
  if (console_fd >= 0) close(console_fd);
  juku_destroy(ctx);
  return 0;
}
