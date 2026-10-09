#include "juku_internal.h"
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <stdio.h> /* vsnprintf only; host output is a callback */

void juku_log(juku *ctx, const char *format, ...) {
  if (!ctx->hooks.log) return;
  char message[1024];
  va_list args;
  va_start(args, format);
  vsnprintf(message, sizeof(message), format, args);
  va_end(args);
  ctx->hooks.log(ctx->hooks.user, message);
}
static const struct { char c; uint8_t col, bit, shift; } KMAP[] = {
  {'a',5,5,0},{'b',4,1,0},{'c',6,1,0},{'d',6,5,0},{'e',6,3,0},{'f',2,5,0},{'g',4,5,0},{'h',0,5,0},
  {'i',14,3,0},{'j',7,5,0},{'k',14,5,0},{'l',13,5,0},{'m',7,1,0},{'n',0,1,0},{'o',13,3,0},{'p',12,3,0},
  {'q',5,3,0},{'r',2,3,0},{'s',1,5,0},{'t',4,3,0},{'u',7,3,0},{'v',2,1,0},{'w',1,3,0},{'x',1,1,0},
  {'y',0,3,0},{'z',5,1,0},
  {'0',12,4,0},{'1',5,4,0},{'2',1,4,0},{'3',6,4,0},{'4',2,4,0},{'5',4,4,0},{'6',0,4,0},{'7',7,4,0},{'8',14,4,0},{'9',13,4,0},
  {'!',5,4,1},{'"',1,4,1},{'#',6,4,1},{'$',2,4,1},{'%',4,4,1},{'&',0,4,1},{'\'',7,4,1},
  {'(',14,4,1},{')',13,4,1},{'_',12,4,1},
  {' ',11,2,0},{'\r',8,5,0},{'\n',8,5,0},{'\t',3,3,0},{'\b',13,2,0},{'\033',3,4,0},
  {'.',13,1,0},{'>',13,1,1},{',',14,1,0},{'<',14,1,1},{'/',12,1,0},{'?',12,1,1},
  {';',11,1,0},{'+',11,1,1},{'-',11,4,0},{'=',11,4,1},{':',10,5,0},{'*',10,5,1},
  {'[',9,3,0},{']',8,3,0},{'\\',11,3,0},{'^',11,3,1},
  {'\x80',9,2,0}, // synthetic PTY byte: factory Down contact (row 6)
  {'\x81',8,4,0}, // synthetic PTY byte: factory Erase contact (row 1)
  {'\x82',4,0,0}, // synthetic PTY byte: factory F5 contact (row 5)
  {'\x83',0,0,0}, // synthetic PTY byte: factory F6 contact (row 5)
  {'\x84',14,0,0}, // synthetic PTY byte: factory F8 contact (row 5)
  {'\x86',14,0,1}, // synthetic PTY byte: factory Shift-F8 contact (row 5)
  {'\x87',3,0,0}, // synthetic PTY byte: factory F1 contact (row 5)
  {'\x88',5,0,0}, // synthetic PTY byte: factory F2 contact (row 5)
  {'\x89',6,0,0}, // synthetic PTY byte: factory F3 contact (row 5)
  {'\x8a',2,0,0}, // synthetic PTY byte: factory F4 contact (row 5)
  {'\x8b',10,2,0}, // synthetic PTY byte: factory Up contact (row 6)
  {'\x8c',12,2,0}, // synthetic PTY byte: factory Right contact (row 6)
  {'\x8d',13,2,0}, // synthetic PTY byte: factory Left contact (row 6)
  {'\x8f',10,2,1}, // synthetic PTY byte: factory Shift-Up contact (row 6)
  {'\x90',9,2,1}, // synthetic PTY byte: factory Shift-Down contact (row 6)
  {'\x91',7,0,0}, // synthetic PTY byte: factory F7 contact (row 5)
};

int juku_is_pit_data_port(juku *ctx, uint8_t port) {
  (void)ctx;
  return port >= 0x10 && port <= 0x1A && (port & 3) != 3;
}

pit_counter* juku_pit_counter_for_port(juku *ctx, uint8_t port) {
  (void)ctx;
  unsigned chip = (port - 0x10) >> 2;
  unsigned channel = port & 3;
  return &ctx->pit_counters[chip][channel];
}

void juku_pit_write(juku *ctx, uint8_t port, uint8_t value) {
  (void)ctx;
  unsigned chip = (port - 0x10) >> 2;
  unsigned reg = port & 3;
  if (reg == 3) {
    unsigned channel = value >> 6;
    unsigned access = (value >> 4) & 3;
    if (channel >= 3) return;  // 8253 has no 8254-style read-back command
    pit_counter* counter = &ctx->pit_counters[chip][channel];
    if (access == 0) {
      // A pending latch owns the output latch until its programmed byte(s)
      // are consumed; later counter-latch commands are ignored.
      if (!counter->latch_valid) {
        counter->output_latch = counter->count_register;
        counter->latch_valid = 1;
        counter->read_phase = 0;
      }
    } else {
      counter->access = (uint8_t)access;
      counter->bcd = value & 1;
      counter->mode = (value >> 1) & 7;
      if (counter->mode > 5) counter->mode &= 3;
      counter->write_phase = 0;
      counter->read_phase = 0;
      counter->latch_valid = 0;
    }
    return;
  }

  pit_counter* counter = &ctx->pit_counters[chip][reg];
  counter->latch_valid = 0;
  counter->read_phase = 0;
  if (counter->access == 1) {
    counter->count_register = value;
  } else if (counter->access == 2) {
    counter->count_register = (uint16_t)value << 8;
  } else if (counter->access == 3) {
    if (!counter->write_phase) {
      counter->write_latch = value;
      counter->write_phase = 1;
      return;
    }
    counter->count_register = (uint16_t)(((uint16_t)value << 8) |
                                         (counter->write_latch & 0xFF));
    counter->write_phase = 0;
  }
}

void juku_video_observe_pit_write(juku *ctx, uint8_t port, uint8_t value) {
  (void)ctx;
  /* MODX's resident console programs D54/D55 with this exact sequence.  The
     resulting timing is a 400x192 bitmap: 50 bytes per raster line and 24
     eight-scanline text rows.  Keep the stock 320x241 view until the complete
     signature is observed so ordinary EktaSoft video remains unchanged. */
  static const uint8_t modx_sequence[][2] = {
    {0x17, 0x73}, {0x11, 0x14}, {0x12, 0x03},
    {0x15, 0x1A}, {0x15, 0x01}, {0x16, 0x45},
  };
  static const uint8_t stock_sequence[][2] = {
    {0x11, 0x24}, {0x12, 0x08}, {0x15, 0x72},
    {0x15, 0x00}, {0x16, 0x25},
  };
  static const uint8_t mode64_sequence[][2] = {
    {0x11, 0x16}, {0x12, 0x04}, {0x15, 0x12},
    {0x15, 0x01}, {0x16, 0x45},
  };
  const unsigned sequence_length =
      (unsigned)(sizeof(modx_sequence) / sizeof(modx_sequence[0]));

  if (port == modx_sequence[ctx->video_modx_sequence][0] &&
      value == modx_sequence[ctx->video_modx_sequence][1]) {
    ctx->video_modx_sequence++;
    if (ctx->video_modx_sequence == sequence_length) {
      ctx->video_stride = 50;
      ctx->video_lines = 192;
      ctx->video_modx_mode = 1;
      ctx->video_console_mode = 3;
      ctx->video_modx_sequence = 0;
      juku_log(ctx, "[VIDEO] recognized MODX 400x192 timing\n");
    }
    return;
  }

  ctx->video_modx_sequence =
      (port == modx_sequence[0][0] && value == modx_sequence[0][1]) ? 1 : 0;

  do {
    const unsigned length = (unsigned)(sizeof(stock_sequence) / sizeof((stock_sequence)[0]));
    if (port == (stock_sequence)[ctx->video_stock_sequence][0] && value == (stock_sequence)[ctx->video_stock_sequence][1]) {
      (ctx->video_stock_sequence)++;
      if ((ctx->video_stock_sequence) == length) {
        ctx->video_stride = (40);
        ctx->video_lines = (241);
        ctx->video_modx_mode = 0;
        ctx->video_console_mode = ((ctx->kbd_s21_config >> 1) & 1);
        (ctx->video_stock_sequence) = 0;
      }
    } else {
      (ctx->video_stock_sequence) = (port == (stock_sequence)[0][0] && value == (stock_sequence)[0][1]) ? 1 : 0;
    }
  } while (0);
  do {
    const unsigned length = (unsigned)(sizeof(mode64_sequence) / sizeof((mode64_sequence)[0]));
    if (port == (mode64_sequence)[ctx->video_64_sequence][0] && value == (mode64_sequence)[ctx->video_64_sequence][1]) {
      (ctx->video_64_sequence)++;
      if ((ctx->video_64_sequence) == length) {
        ctx->video_stride = (48);
        ctx->video_lines = (201);
        ctx->video_modx_mode = 0;
        ctx->video_console_mode = (2);
        (ctx->video_64_sequence) = 0;
      }
    } else {
      (ctx->video_64_sequence) = (port == (mode64_sequence)[0][0] && value == (mode64_sequence)[0][1]) ? 1 : 0;
    }
  } while (0);
}

uint8_t juku_pit_read(juku *ctx, uint8_t port) {
  (void)ctx;
  pit_counter* counter = juku_pit_counter_for_port(ctx, port);
  uint16_t value = counter->latch_valid
      ? counter->output_latch : counter->count_register;
  uint8_t result;
  if (counter->access == 2) {
    result = (uint8_t)(value >> 8);
    counter->latch_valid = 0;
  } else if (counter->access == 3 && counter->read_phase) {
    result = (uint8_t)(value >> 8);
    counter->read_phase = 0;
    counter->latch_valid = 0;
  } else {
    result = (uint8_t)value;
    if (counter->access == 3) counter->read_phase = 1;
    else counter->latch_valid = 0;
  }
  return result;
}

void juku_pit_init(juku *ctx) {
  (void)ctx;
  for (unsigned chip = 0; chip < 3; ++chip)
    for (unsigned channel = 0; channel < 3; ++channel)
      ctx->pit_counters[chip][channel].access = 3;
}

uint8_t juku_apply_ram_fault(juku *ctx, uint16_t address, uint8_t value) {
  (void)ctx;
  if (!ctx->ram_fault_enabled || (!ctx->ram_fault_all && address != ctx->ram_fault_addr))
    return value;
  return (uint8_t)((value & (uint8_t)~ctx->ram_fault_stuck_low) |
                   ctx->ram_fault_stuck_high);
}

uint16_t juku_map_ram_address(juku *ctx, uint16_t address) {
  (void)ctx;
  if (ctx->ram_alias_enabled && (address >> 8) == ctx->ram_alias_page_b)
    return (uint16_t)(((uint16_t)ctx->ram_alias_page_a << 8) | (address & 0xFF));
  return address;
}

uint8_t juku_dram_row_from_address(juku *ctx, uint16_t address) {
  (void)ctx;
  /*
   * D48/D49 select CPU A0..A7 in the populated-bank /RAS phase and A8..A15
   * for /CAS.  MK4564/2164-class 128-cycle refresh uses physical MA0..MA6;
   * MA7 (pin 9) is irrelevant.  The inverting KP14 mux changes row polarity,
   * but not which logical addresses share a row, so normalize it away here.
   */
  return (uint8_t)(address & 0x7F);
}

void juku_dram_touch(juku *ctx, i8080* cpu, uint16_t physical_address) {
  (void)ctx;
  if (!ctx->dram_retention_cycles || !ctx->dram_retention_armed || !cpu) return;
  uint8_t row = juku_dram_row_from_address(ctx, physical_address);
  if (!ctx->dram_coverage_count ||
      cpu->cyc - ctx->dram_coverage_start > ctx->dram_retention_cycles) {
    memset(ctx->dram_coverage_seen, 0, sizeof(ctx->dram_coverage_seen));
    ctx->dram_coverage_count = 0;
    ctx->dram_coverage_start = cpu->cyc;
  }
  if (!ctx->dram_coverage_seen[row]) {
    ctx->dram_coverage_seen[row] = 1;
    ctx->dram_coverage_count++;
    if (ctx->dram_coverage_count == 128 && !ctx->dram_full_coverage_reported) {
      ctx->dram_full_coverage_reported = 1;
      juku_log(ctx, "[DRAM] observed all 128 refresh rows in %lu cycles at cyc=%lu\n",
              cpu->cyc - ctx->dram_coverage_start, cpu->cyc);
    }
  }
  unsigned long age = cpu->cyc - ctx->dram_last_refresh[row];
  if (age > ctx->dram_retention_cycles) {
    for (unsigned address = 0; address < MEM_SIZE; address++)
      if (juku_dram_row_from_address(ctx, (uint16_t)address) == row)
        ctx->ram[address] ^= 0xFF;
    ctx->dram_decay_count++;
    if (ctx->dram_decay_count <= 32)
      juku_log(ctx, "[DRAM] decayed refresh row=%02X age=%lu cyc=%lu count=%lu\n",
              row, age, cpu->cyc, ctx->dram_decay_count);
  }
  ctx->dram_last_refresh[row] = cpu->cyc;
}

unsigned long juku_pit_effective_divisor(juku *ctx, const pit_counter* counter) {
  (void)ctx;
  unsigned long raw = counter->count_register;
  if (!counter->bcd) return raw ? raw : 65536UL;
  unsigned long divisor = 0, place = 1;
  for (unsigned shift = 0; shift < 16; shift += 4) {
    divisor += ((raw >> shift) & 0x0F) * place;
    place *= 10;
  }
  return divisor ? divisor : 10000UL;
}

void juku_usart_update_pit_timing(juku *ctx) {
  (void)ctx;
  if (!ctx->usart_pit_clock || !ctx->usart_pit_divisor) return;
  pit_counter* baud_counter = &ctx->pit_counters[2][0];
  if ((baud_counter->mode == 2 || baud_counter->mode == 3) &&
      ctx->usart_pit_divisor < 2) {
    ctx->usart_pit_clock_valid = 0;
    juku_log(ctx, "[USART] invalid D57 mode=%u divisor=%lu; no periodic baud clock\n",
            baud_counter->mode, ctx->usart_pit_divisor);
    return;
  }
  unsigned factor;
  switch (ctx->usart.mode_word & 3) {
    case 1: factor = 1; break;
    case 2: factor = 16; break;
    case 3: factor = 64; break;
    default: return;  /* synchronous mode */
  }
  unsigned data_bits = 5 + ((ctx->usart.mode_word >> 2) & 3);
  unsigned wire_bits_x2 = 2 * (1 + data_bits);
  if (ctx->usart.mode_word & 0x10) wire_bits_x2 += 2;  /* parity */
  switch ((ctx->usart.mode_word >> 6) & 3) {
    case 1: wire_bits_x2 += 2; break;  /* one stop bit */
    case 2: wire_bits_x2 += 3; break;  /* 1.5 stop bits */
    case 3: wire_bits_x2 += 4; break;  /* two stop bits */
    default: return;
  }
  if (ctx->usart_pit_cpu_hz)
    ctx->usart.byte_cycles =
        (ctx->usart_pit_cpu_hz * wire_bits_x2 * factor * ctx->usart_pit_divisor * 13UL) /
        (2UL * 16000000UL);
  else
    ctx->usart.byte_cycles =
        (2000000UL * wire_bits_x2 * factor * ctx->usart_pit_divisor * 13UL) /
        (2UL * 16000000UL);
  if (!ctx->usart.byte_cycles) ctx->usart.byte_cycles = 1;
  ctx->usart_pit_clock_valid = 1;
  juku_log(ctx, "[USART] D57 divisor=%lu -> byte_cycles=%lu x%u mode=%02X\n",
          ctx->usart_pit_divisor, ctx->usart.byte_cycles, factor, ctx->usart.mode_word);
}

void juku_usart_update_irq_edges(juku *ctx) {
  (void)ctx;
  int tx_level = ctx->usart.enabled && ctx->usart_tx_irq_armed &&
                 (ctx->usart.command & 0x01) && !ctx->usart.fault_tx_stuck &&
                 !ctx->usart.tx_holding_full;
  int rx_level = ctx->usart.enabled && (ctx->usart.command & 0x04) && ctx->usart.rx_ready;
  if (tx_level && !ctx->usart_tx_irq_level) ctx->usart_tx_irq_pending = 1;
  if (rx_level && !ctx->usart_rx_irq_level) ctx->usart_rx_irq_pending = 1;
  ctx->usart_tx_irq_level = tx_level;
  ctx->usart_rx_irq_level = rx_level;
}

void juku_usart_reset(juku *ctx) {
  (void)ctx;
  if (ctx->usart.fault_tx_stuck && !ctx->usart.fault_tx_stuck_permanent) {
    ctx->usart.fault_tx_stuck_once_recoveries++;
    juku_log(ctx, "[USART] one-shot TxRDY stall cleared by 8251 reset\n");
  }
  /* A reset empties the transmitter.  A configured permanent stall becomes
     active only after the next data write fills the holding register. */
  ctx->usart.fault_tx_stuck = 0;
  ctx->usart.expect_mode = 1;
  ctx->usart.mode_word = 0;
  ctx->usart.command = 0;
  ctx->usart.rx_ready = 0;
  ctx->usart.rx_errors = 0;
  ctx->usart.tx_holding_full = 0;
  ctx->usart.tx_busy = 0;
  ctx->usart_host_sync_armed = 0;
  ctx->usart_host_sync_waiting = 0;
  ctx->usart_tx_irq_armed = 0;
  ctx->usart_tx_irq_level = ctx->usart_rx_irq_level = 0;
  ctx->usart_tx_irq_pending = ctx->usart_rx_irq_pending = 0;
}

void juku_usart_poll(juku *ctx, unsigned long cyc) {
  (void)ctx;
  if (!ctx->usart.enabled) return;
  if (ctx->usart_pit_clock && !ctx->usart_pit_clock_valid) return;
  if (ctx->usart.tx_busy && cyc >= ctx->usart.tx_complete_cyc) {
    int written = ctx->hooks.serial_write ? ctx->hooks.serial_write(ctx->hooks.user, ctx->usart.tx_shift_data) : 0;
    if (written == 1) {
      ctx->usart.tx_busy = 0;
      ctx->usart.tx_bytes++;
      if (ctx->usart_host_sync_armed && !ctx->usart.tx_holding_full) {
        ctx->usart_host_sync_armed = 0;
        ctx->usart_host_sync_waiting = 1;
      }
      if (ctx->usart.tx_holding_full)
        ctx->usart.tx_transfer_cyc = cyc + ctx->usart.transfer_cycles;
    }
  }
  if (!ctx->usart.fault_tx_stuck && ctx->usart.tx_holding_full && !ctx->usart.tx_busy &&
      cyc >= ctx->usart.tx_transfer_cyc) {
    ctx->usart.tx_shift_data = ctx->usart.tx_data;
    ctx->usart.tx_holding_full = 0;
    ctx->usart.tx_busy = 1;
    ctx->usart.tx_complete_cyc = cyc + ctx->usart.byte_cycles;
  }
  /* Bytes sent while RxEnable is clear have already passed on a physical
     wire; they cannot wait in an invisible PTY FIFO and appear after firmware
     enables the 8251. Drain that emulator-only backlog. This matters when a
     host probes continuously while a ROM command is still initializing D11.
     Once enabled, preserve byte timing and overrun behavior below. */
  if (!(ctx->usart.command & 0x04)) {
    uint8_t discarded[256];
    for (;;) {
      int received = ctx->hooks.serial_read ? ctx->hooks.serial_read(ctx->hooks.user, discarded, sizeof(discarded)) : 0;
      if (received > 0) {
        ctx->usart.rx_disabled_bytes += (unsigned long)received;
        continue;
      }

      break;
    }
  }
  /* The serial line keeps shifting while the receive data register is full.
     Do not let the host PTY become an impossible extra FIFO: at each complete
     character time, consume the next wire byte.  If firmware has not read the
     previous byte, latch OE and discard the newcomer. */
  while ((ctx->usart.command & 0x04) && cyc >= ctx->usart.rx_next_cyc) {
    uint8_t value;
    int received = ctx->hooks.serial_read ? ctx->hooks.serial_read(ctx->hooks.user, &value, 1) : 0;
    if (received == 1) {
      ctx->usart_host_sync_waiting = 0;
      if (ctx->usart.rx_ready) {
        ctx->usart.rx_errors |= 0x10;
        ctx->usart.rx_overruns++;
        if (ctx->usart.rx_overruns <= 20)
          juku_log(ctx, "[USART] Rx overrun #%lu byte=%lu data=%02X cyc=%lu "
                  "next=%lu mode=%d command=%02X\n",
                  ctx->usart.rx_overruns, ctx->usart.rx_bytes + 1, value, cyc,
                  ctx->usart.rx_next_cyc, ctx->mode, ctx->usart.command);
      } else {
        ctx->usart.rx_data = value;
        ctx->usart.rx_ready = 1;
      }
      ctx->usart.rx_bytes++;
      /* The receive clock is independent of the CPU.  Advance from the
         scheduled wire time, not from a late firmware poll; otherwise every
         slow instruction silently stretches the emulated serial line and
         makes a one-byte 8251 impossible to overrun. */
      ctx->usart.rx_next_cyc += ctx->usart.byte_cycles;
      continue;
    }

    /* An unpaced CPU can consume a firmware timeout before a native helper
       process gets another scheduler slice.  Once the target has transmitted,
       an explicitly synchronized PTY may wait for the first reply byte.  The
       byte still enters the 8251 at the modeled wire time below; this only
       coordinates two host processes at their asynchronous boundary. */
    if (ctx->usart_host_sync_waiting && ctx->usart_host_sync_ms) {
      if (ctx->hooks.serial_wait && ctx->hooks.serial_wait(ctx->hooks.user, ctx->usart_host_sync_ms)) continue;
      ctx->usart_host_sync_waiting = 0;
    }
    /* No character is currently on the wire.  Anchor the next batch at the
       present cycle so an idle interval cannot accumulate fictitious slots;
       once a batch starts, the loop above preserves every real slot. */
    ctx->usart.rx_next_cyc = cyc;
    break;
  }
  juku_usart_update_irq_edges(ctx);
}

uint8_t juku_usart_status(juku *ctx) {
  (void)ctx;
  if (ctx->usart.fault_tx_not_ready_once_after_enabled &&
      !ctx->usart.fault_tx_stuck_once_fired &&
      ctx->usart.tx_bytes >= ctx->usart.fault_tx_not_ready_once_after) {
    ctx->usart.fault_tx_stuck = 1;
    ctx->usart.fault_tx_stuck_once_fired = 1;
    juku_log(ctx, "[USART] injected one-shot TxRDY stall after byte=%lu\n",
            ctx->usart.tx_bytes);
  }
  uint8_t tx_ready = (ctx->usart.fault_tx_stuck || ctx->usart.tx_holding_full) ? 0 : 0x01;
  uint8_t tx_empty = (!ctx->usart.fault_tx_stuck && !ctx->usart.tx_holding_full &&
                      !ctx->usart.tx_busy) ? 0x04 : 0;
  if (ctx->usart.fault_tx_empty_low_after_enabled &&
      ctx->usart.tx_bytes >= ctx->usart.fault_tx_empty_low_after)
    tx_empty = 0;
  return (uint8_t)(tx_ready | tx_empty | (ctx->usart.rx_ready ? 0x02 : 0) |
                   ctx->usart.rx_errors);
}

uint8_t juku_usart_read(juku *ctx, int control, unsigned long cyc) {
  (void)ctx;
  juku_usart_poll(ctx, cyc);
  if (control) return juku_usart_status(ctx);
  uint8_t value = ctx->usart.rx_data;
  ctx->usart.rx_ready = 0;
  juku_usart_update_irq_edges(ctx);
  return value;
}

void juku_usart_write(juku *ctx, int control, uint8_t value, unsigned long cyc) {
  (void)ctx;
  juku_usart_poll(ctx, cyc);
  if (control) {
    if (ctx->usart.expect_mode) {
      ctx->usart.mode_word = value;
      ctx->usart.expect_mode = 0;
      juku_usart_update_pit_timing(ctx);
    } else if (value & 0x40) {
      juku_usart_reset(ctx);
    } else {
      uint8_t old_command = ctx->usart.command;
      ctx->usart.command = value;
      if ((old_command & 0x01) && !(value & 0x01)) {
        // NetBios deliberately drops and raises TxEN when a complete frame is
        // queued.  Treat that as the interrupt arm/ack boundary; the initial
        // 8251 enable occurs before its transmit descriptor is initialized.
        ctx->usart_tx_irq_armed = 1;
        ctx->usart_tx_irq_pending = 0;
        if (ctx->usart_host_sync_ms) {
          if (ctx->usart.tx_busy || ctx->usart.tx_holding_full)
            ctx->usart_host_sync_armed = 1;
          else
            ctx->usart_host_sync_waiting = 1;
        }
      }
      /* ER (bit 4) resets PE/OE/FE error latches; it does not consume the
         receive data register or clear RxRDY.  Preserving an unread byte is
         essential across half-duplex TxEN turnarounds. */
      if (value & 0x10) ctx->usart.rx_errors = 0;
    }
  } else if ((ctx->usart.command & 0x01) && !ctx->usart.tx_holding_full) {
    ctx->usart.tx_data = value;
    ctx->usart.tx_holding_full = 1;
    if (ctx->usart.fault_tx_stuck_permanent)
      ctx->usart.fault_tx_stuck = 1;
    if (ctx->usart.fault_tx_stuck_once_enabled &&
        !ctx->usart.fault_tx_stuck_once_fired &&
        value == ctx->usart.fault_tx_stuck_once_value) {
      ctx->usart.fault_tx_stuck = 1;
      ctx->usart.fault_tx_stuck_once_fired = 1;
      juku_log(ctx, "[USART] injected one-shot TxRDY stall on data=%02X at byte=%lu\n",
              value, ctx->usart.tx_bytes);
    }
    if (!ctx->usart.tx_busy)
      ctx->usart.tx_transfer_cyc = cyc + ctx->usart.transfer_cycles;
  }
  juku_usart_update_irq_edges(ctx);
}

void juku_set_mode(juku *ctx, int m) {
  (void)ctx;
  if (m != ctx->mode) {
    if (ctx->bank_trace)
      juku_log(ctx, "[BANK] mode %d -> %d  (portC=0x%02X)\n", ctx->mode, m, ctx->portc);
    ctx->mode = m;
    if (m == 3 && !ctx->usart.all_ram_seen) {
      ctx->usart.all_ram_seen = 1;
      ctx->usart.rx_overruns_at_all_ram = ctx->usart.rx_overruns;
    }
    ctx->mode_switches++;
  }
}

int juku_overlay(juku *ctx, uint16_t a, unsigned* idx) {
  (void)ctx;
  switch (ctx->mode) {
    case 0: if (a <= 0x3FFF) { *idx = a; return 1; } return 0;
    case 1: if (a >= 0xD800) { *idx = 0x1800 + (a - 0xD800); return 1; } return 0;
    case 2: if (a >= 0x4000 && a <= 0xBFFF) return 2;
            if (a >= 0xD800) { *idx = 0x1800 + (a - 0xD800); return 1; } return 0;
    default: return 0;            // mode 3: all RAM
  }
}

void juku_trace_bus_event(juku *ctx, const char* kind, uint16_t address, uint8_t data) {
  (void)ctx;
  dac_trace_emit(&ctx->bus_trace, kind, address, data, ctx->cpu.cyc, 0);
}

uint8_t juku_peek_byte(juku *ctx, uint16_t address) {
  (void)ctx;
  unsigned idx = 0;
  int ov = juku_overlay(ctx, address, &idx);
  if (ov == 1)
    return ctx->rom[idx];
  if (ov == 2)
    return ctx->cart_enabled ? ctx->cart[address - 0x4000] : 0xFF;
  return juku_apply_ram_fault(ctx, address, ctx->ram[juku_map_ram_address(ctx, address)]);
}

uint16_t juku_peek_word(juku *ctx, uint16_t address) {
  (void)ctx;
  uint8_t low = juku_peek_byte(ctx, address);
  uint8_t high = juku_peek_byte(ctx, (uint16_t)(address + 1));
  return (uint16_t)(low | ((uint16_t)high << 8));
}

uint8_t juku_rb(juku *ctx, void* u, uint16_t a) {
  (void)ctx;
  i8080* cpu = (i8080*)u;
  uint16_t physical_a = a;
  unsigned idx = 0;
  uint8_t v;
  int ov = juku_overlay(ctx, physical_a, &idx);
  if (ov == 1) {
    unsigned ordinal = ++ctx->rom_read_burst_count;
    if (ctx->rom_consecutive_a12_low && ordinal >= 2) idx &= ~0x1000u;
    v = ctx->rom[idx];
  }
  else if (ov == 2) {
    ctx->rom_read_burst_count = 0;
    v = ctx->cart_enabled ? ctx->cart[physical_a - 0x4000] : 0xFF;
  }
  else {
    ctx->rom_read_burst_count = 0;
    uint16_t mapped = juku_map_ram_address(ctx, physical_a);
    juku_dram_touch(ctx, cpu, mapped);
    v = juku_apply_ram_fault(ctx, physical_a, ctx->ram[mapped]);
  }
  if (ctx->exec_byte_fault_enabled && a == ctx->exec_byte_fault_addr && cpu &&
      (cpu->pc == a || cpu->pc == (uint16_t)(a + 1)))
    v = ctx->exec_byte_fault_value;
  if (ctx->watch_address >= 0 && a >= (uint16_t)ctx->watch_address &&
      a <= (uint16_t)ctx->watch_address_end)
    juku_log(ctx, "[WATCH] MR %04X=%02X pc=%04X cyc=%lu\n",
            a, v, cpu ? cpu->pc : 0, cpu ? cpu->cyc : 0);
  if (ctx->hooks.memory_read) ctx->hooks.memory_read(ctx->hooks.user, a, v);
  juku_trace_bus_event(ctx, "MR", a, v);
  return v;
}

char juku_kbd_current_char(juku *ctx) {
  (void)ctx;
  if (ctx->kbd_pc_trigger_active) return ctx->kbd_pc_trigger_char;
  if (!ctx->kbd_str) return 0;
  if (ctx->kbd_str == ctx->console_queue && ctx->kbd_pos >= ctx->console_visible_len) return 0;
  return ctx->kbd_str[ctx->kbd_pos];
}

int juku_vram_pixel(juku *ctx, int x, int y) {
  (void)ctx;
  if (x < 0 || x >= (int)ctx->video_stride * 8 ||
      y < 0 || y >= (int)ctx->video_lines) return 0;
  uint8_t byte = ctx->ram[VRAM_BASE + y * ctx->video_stride + (x >> 3)];
  return (byte >> (7 - (x & 7))) & 1;
}

int juku_ekdos_prompt_visible(juku *ctx) {
  (void)ctx;
  static const char* stock_pattern[] = {
    "................",
    "....#......#....",
    "...#.#......#...",
    "..#...#......#..",
    "..#...#.......#.",
    "..#####......#..",
    "..#...#.....#...",
    "..#...#....#....",
    "................",
    "................",
  };
  static const char* modx_pattern[] = {
    "..........",
    ".###......",
    "#...#.#...",
    "#...#..#..",
    "#####...#.",
    "#...#..#..",
    "#...#.#...",
    "..........",
  };
  const char** pattern = ctx->video_modx_mode ? modx_pattern : stock_pattern;
  const int ph = ctx->video_modx_mode
      ? (int)(sizeof(modx_pattern) / sizeof(modx_pattern[0]))
      : (int)(sizeof(stock_pattern) / sizeof(stock_pattern[0]));
  const int pw = ctx->video_modx_mode ? 10 : 16;
  for (int y = 0; y <= (int)ctx->video_lines - ph; y++) {
    for (int x = 0; x < 3; x++) {
      int ok = 1;
      for (int dy = 0; dy < ph && ok; dy++) {
        for (int dx = 0; dx < pw; dx++) {
          if (juku_vram_pixel(ctx, x + dx, y + dy) != (pattern[dy][dx] == '#')) {
            ok = 0;
            break;
          }
        }
      }
      if (ok) return 1;
    }
  }
  return 0;
}

uint8_t juku_kbd_portb(juku *ctx, const i8080* cpu) {
  (void)ctx;
  // S21.1..8 occupy columns 8..15 on active-low CONTRDAT/PB5. Keep this
  // electrical behavior independent of the caller's PC so RAM-owned systems
  // can sample the same switches after the stock ROM has disappeared.
  int s21_bit = (ctx->kbd_col >= 8 && ctx->kbd_col <= 15) ? 15 - ctx->kbd_col : -1;
  int s21_closed = s21_bit >= 0 && (ctx->kbd_s21_config & (1u << s21_bit));
  uint8_t contrdat = (s21_bit >= 0 && !s21_closed) ? 0x20 : 0;
  uint8_t idle = (uint8_t)(KBD_NONE | contrdat);
  if (ctx->g_vw < ctx->kbd_start_vram) return idle;              // default waits until the ekta37 banner is drawn
  char current = juku_kbd_current_char(ctx);
  int hold_frames = ctx->kbd_pc_trigger_active && ctx->kbd_pc_trigger_hold_frames > 0
                    ? ctx->kbd_pc_trigger_hold_frames : ctx->kbd_hold_frames;
  char c = (current && ctx->kbd_phase < hold_frames) ? current : 0;
  if (c == '|') return idle;                           // prompt wait marker, not a typed key
  int shift = 0, ctrl = 0, col = -1, bit = -1;
  if (c) {
    char lc = c;
    if ((unsigned char)c == 0x85) {                    // synthetic Ctrl-Up / Home
      col = 10;
      bit = 2;
      ctrl = 1;
    }
    if ((unsigned char)c == 0x8e) {                    // synthetic Ctrl-Down / End
      col = 9;
      bit = 2;
      ctrl = 1;
    }
    // Prefer a dedicated physical key (Tab, Return, Backspace, Escape) over
    // spelling the same ASCII control byte as Ctrl+letter.
    for (unsigned i = 0; i < sizeof(KMAP)/sizeof(KMAP[0]); i++)
      if (KMAP[i].c == lc) { col = KMAP[i].col; bit = KMAP[i].bit; shift |= KMAP[i].shift; break; }
    if (col < 0 && c >= 1 && c <= 26) {
      // The interactive PTY expresses Ctrl-A..Ctrl-Z as their ordinary
      // ASCII control bytes. Translate those bytes back to the physical
      // letter contact plus Juku's dedicated active-low CTRL return.
      lc = (char)('a' + c - 1);
      ctrl = 1;
    } else if (c >= 'A' && c <= 'Z') {
      lc = (char)(c + 32);
      shift = 1;
    }
    if (col < 0)
      for (unsigned i = 0; i < sizeof(KMAP)/sizeof(KMAP[0]); i++)
        if (KMAP[i].c == lc) { col = KMAP[i].col; bit = KMAP[i].bit; shift |= KMAP[i].shift; break; }
  }
  uint8_t pb = (uint8_t)(0xC0 | contrdat);
  if (shift) pb &= (uint8_t)~0x40;                     // SHIFT1 held = bit6 low (active-low)
  if (ctrl) pb &= (uint8_t)~0x80;                      // CTRL held = bit7 low (active-low)
  if (c && col == ctx->kbd_col)
    pb |= (uint8_t)(((~bit) & 7) << 1);                // 74148 code in b1-3, GS active (b0=0)
  else
    pb |= 0x0F;                                        // no key here: code=7 + GS released (b0=1)
  if (ctx->kbd_trace && c && col == ctx->kbd_col)
    juku_log(ctx, "[KBD] scan char=%02X pos=%d phase=%d col=%d pb=%02X pc=%04X cyc=%lu\n",
            (unsigned char)c, ctx->kbd_pos, ctx->kbd_phase, col, pb,
            cpu ? cpu->pc : 0, cpu ? cpu->cyc : 0);
  return pb;
}

void juku_wb(juku *ctx, void* u, uint16_t a, uint8_t v) {
  (void)ctx;
  ctx->rom_read_burst_count = 0;
  if (ctx->watch_address >= 0 && a >= (uint16_t)ctx->watch_address &&
      a <= (uint16_t)ctx->watch_address_end) {
    ctx->watch_write_previous_address = ctx->watch_write_last_address;
    ctx->watch_write_previous_value = ctx->watch_write_last_value;
    ctx->watch_write_previous_pc = ctx->watch_write_last_pc;
    ctx->watch_write_previous_cycle = ctx->watch_write_last_cycle;
    ctx->watch_write_last_address = a;
    ctx->watch_write_last_value = v;
    ctx->watch_write_last_pc = u ? ((i8080*)u)->pc : 0;
    ctx->watch_write_last_cycle = u ? ((i8080*)u)->cyc : 0;
    ctx->watch_write_count++;
    juku_log(ctx, "[WATCH] MW %04X=%02X pc=%04X cyc=%lu\n",
            a, v, u ? ((i8080*)u)->pc : 0, u ? ((i8080*)u)->cyc : 0);
  }
  juku_trace_bus_event(ctx, "MW", a, v);
  unsigned idx = 0;
  int ov = juku_overlay(ctx, a, &idx);
  // EktaSoft 3.7's low-ROM dispatcher writes its return frame behind page-zero
  // ROM. High-ROM and cartridge windows remain read-only overlays; allowing
  // those writes corrupts the independently guarded Monitor 3.3 framebuffer.
  if (ov && !(ctx->mode == 0 && a <= 0x3FFF)) return;
  if (ctx->ram_drop_write_enabled && ctx->ram_drop_write_remaining &&
      a == ctx->ram_drop_write_addr && v == ctx->ram_drop_write_value) {
    ctx->ram_drop_write_remaining--;
    juku_log(ctx, "[RAM] dropped write address=0x%04X value=0x%02X remaining=%u\n",
            a, v, ctx->ram_drop_write_remaining);
    return;
  }
  uint16_t mapped = juku_map_ram_address(ctx, a);
  juku_dram_touch(ctx, (i8080*)u, mapped);
  ctx->ram[mapped] = juku_apply_ram_fault(ctx, a, v);
  ctx->wpage[a >> 8]++;
  if (a >= VRAM_BASE) {            // for CI: stop+dump after N video writes (match HDL)
    if (ctx->g_vw == 0) {
      unsigned long cyc = u ? ((i8080*)u)->cyc : 0;
      juku_log(ctx, "[VRAM] first video write @0x%04X cyc=%lu\n",
              a, cyc);
    }
    ctx->g_vw++;
  }
}

int juku_take_pic_irq(juku *ctx, i8080* cpu, unsigned irq, const char* source,
                        unsigned long* log_count) {
  (void)ctx;
  if (!cpu || irq > 7 || !cpu->iff || (ctx->pic_mask & (1u << irq))) return 0;

  uint16_t vec = ((uint16_t)ctx->pic_icw2 << 8) | (ctx->pic_icw1 & 0xE0) | (irq << 2);
  if ((*log_count)++ < 3)
    juku_log(ctx, "[IRQ] %s #%lu g_vw=%lu cyc=%lu pc=%04X irq=%u "
            "icw1=%02X icw2=%02X mask=%02X vec=%04X\n",
            source, *log_count, ctx->g_vw, cpu->cyc, cpu->pc, irq,
            ctx->pic_icw1, ctx->pic_icw2, ctx->pic_mask, vec);

  // The 8259 supplies an MCS-80 CALL over three INTA cycles.  The functional
  // cosim performs the resulting call directly while retaining those bus
  // events for the unified trace contract.
  juku_trace_bus_event(ctx, "IA", 0, 0xCD);
  juku_trace_bus_event(ctx, "IA", 0, (uint8_t)vec);
  juku_trace_bus_event(ctx, "IA", 0, (uint8_t)(vec >> 8));
  if (cpu->halted) cpu->halted = 0;
  juku_wb(ctx, 0, (uint16_t)(cpu->sp - 1), cpu->pc >> 8);
  juku_wb(ctx, 0, (uint16_t)(cpu->sp - 2), cpu->pc & 0xFF);
  cpu->sp -= 2;
  cpu->iff = 0;
  cpu->pc = vec;
  return 1;
}

void juku_sync_fdc_time(juku *ctx, i8080* cpu) {
  (void)ctx;
  if (!ctx->fdc_enabled || !cpu || cpu->cyc <= ctx->fdc_last_cyc) return;
  juku_fdc_tick(&ctx->fdc, (unsigned)(cpu->cyc - ctx->fdc_last_cyc));
  ctx->fdc_last_cyc = cpu->cyc;
}

uint8_t juku_pin(juku *ctx, void* u, uint8_t p) {
  (void)ctx;
  ctx->rom_read_burst_count = 0;
  i8080* cpu = (i8080*)u;
  juku_sync_fdc_time(ctx, cpu);
  if (!ctx->in_seen[p]) { ctx->in_seen[p] = 1; juku_log(ctx, "[IN ] first read  port 0x%02X\n", p); }
  if (ctx->timing_log && ctx->in_count[p] == 0) {
    juku_log(ctx, "[IOT] first IN  port 0x%02X cyc=%lu pc=%04X g_vw=%lu\n",
            p, cpu ? cpu->cyc : 0, cpu ? cpu->pc : 0, ctx->g_vw);
  }
  ctx->in_count[p]++;
  uint8_t value;
  if (p == 0x05 && ctx->kbd_enabled) value = juku_kbd_portb(ctx, cpu);          // 8255 Port B = keyboard 74148/config scan
  else if (p == 0x06) value = ctx->portc;  // Port C latch, including BSR writes
  else if (ctx->usart.enabled && p >= 0x08 && p <= 0x0B)
    value = juku_usart_read(ctx, p & 1, cpu ? cpu->cyc : 0);
  else if (ctx->fdc_enabled && p >= 0x1C && p <= 0x1F) {
    value = juku_fdc_read(&ctx->fdc, p & 3);
    if (ctx->fdc_bus_invert) value = (uint8_t)~value;
    if (p == 0x1F) ctx->fdc_data_reads++;
  }
  else if (juku_is_pit_data_port(ctx, p)) value = juku_pit_read(ctx, p);
  // Optional expansion hardware occupies F0h-F3h in some software paths.
  // With no card installed the Multibus data lines float high; returning the
  // generic zero-valued output latch here traps NetBios forever in its F1h
  // ready poll before it can initialize the onboard 8251 serial link.
  else if (p >= 0xF0 && p <= 0xF3) value = 0xFF;
  else value = ctx->out_last[p];              // mimic 8255 output-latch readback; 0 if never written
  if (p == 0x01 && ctx->pic_fault_enabled)
    value = (uint8_t)((value & (uint8_t)~ctx->pic_fault_stuck_low) |
                      ctx->pic_fault_stuck_high);
  if (p == ctx->ppi_fault_port && ctx->ppi_fault_enabled)
    value = (uint8_t)((value & (uint8_t)~ctx->ppi_fault_stuck_low) |
                      ctx->ppi_fault_stuck_high);
  if (p == ctx->pit_fault_port && ctx->pit_fault_enabled)
    value = (uint8_t)((value & (uint8_t)~ctx->pit_fault_stuck_low) |
                      ctx->pit_fault_stuck_high);
  if (ctx->io_trace) {
    juku_log(ctx, "[IOSEQ] IN  port=0x%02X value=0x%02X cyc=%lu pc=%04X g_vw=%lu count=%lu\n",
            p, value, cpu ? cpu->cyc : 0, cpu ? cpu->pc : 0, ctx->g_vw, ctx->in_count[p]);
  }
  juku_trace_bus_event(ctx, "IR", p, value);
  return value;
}

void juku_pout(juku *ctx, void* u, uint8_t p, uint8_t v) {
  (void)ctx;
  ctx->rom_read_burst_count = 0;
  juku_trace_bus_event(ctx, "IW", p, v);
  i8080* cpu = (i8080*)u;
  juku_sync_fdc_time(ctx, cpu);
  if (!ctx->out_seen[p]) { ctx->out_seen[p] = 1; juku_log(ctx, "[OUT] first write port 0x%02X = 0x%02X\n", p, v); }
  if (ctx->timing_log && ctx->out_count[p] == 0) {
    juku_log(ctx, "[IOT] first OUT port 0x%02X val=0x%02X cyc=%lu pc=%04X g_vw=%lu\n",
            p, v, cpu ? cpu->cyc : 0, cpu ? cpu->pc : 0, ctx->g_vw);
  }
  ctx->out_count[p]++;
  ctx->out_last[p] = v;
  if (ctx->io_trace) {
    juku_log(ctx, "[IOSEQ] OUT port=0x%02X value=0x%02X cyc=%lu pc=%04X g_vw=%lu count=%lu\n",
            p, v, cpu ? cpu->cyc : 0, cpu ? cpu->pc : 0, ctx->g_vw, ctx->out_count[p]);
  }
  if (ctx->fdc_enabled && p >= 0x1C && p <= 0x1F) {
    juku_fdc_write(&ctx->fdc, p & 3, ctx->fdc_bus_invert ? (uint8_t)~v : v);
    /* The instruction-granular cosim has no model of the Juku's I/O wait
     * states.  As in rombios_fdc_write_test, start the 512-byte firmware
     * stream immediately; the controller-level test retains and checks the
     * exact WD1793 write lead-in timing. */
    const uint8_t fdc_value = ctx->fdc_bus_invert ? (uint8_t)~v : v;
    if (p == 0x1C && (fdc_value & 0xE0) == 0xA0)
      ctx->fdc.write_sector_lead_pending = 0;
  }
  if (ctx->usart.enabled && p >= 0x08 && p <= 0x0B)
    juku_usart_write(ctx, p & 1, v, cpu ? cpu->cyc : 0);
  if (p >= 0x10 && p <= 0x1B) {
    juku_pit_write(ctx, p, v);
    if (p <= 0x17) juku_video_observe_pit_write(ctx, p, v);
    if (ctx->usart_pit_clock && p == 0x18 && v) {
      /* D57 CLK0 is 16 MHz / 13.  Preserve the PIT's BCD interpretation and
         recompute after either the count or the 8251 x1/x16/x64 mode changes. */
      ctx->usart_pit_divisor =
          juku_pit_effective_divisor(ctx, &ctx->pit_counters[2][0]);
      juku_usart_update_pit_timing(ctx);
    }
  }

  if (p == 0x04) ctx->kbd_col = v & 0x0F;   // 8255 Port A low nibble = keyboard column select

  // 8259 PIC programming (port 0x00 = A0=0, port 0x01 = A0=1)
  if (p == 0x00) { if (v & 0x10) { ctx->pic_icw1 = v; ctx->pic_expect_icw2 = 1; } }   // ICW1
  else if (p == 0x01) {
    if (ctx->pic_expect_icw2) { ctx->pic_icw2 = v; ctx->pic_expect_icw2 = 0; }             // ICW2 (vector hi)
    else ctx->pic_mask = v;                                                       // OCW1 (mask)
  }

  // 8255#0 Port C controls the memory view (ports 0x04..0x07)
  if (p == 0x06) {                 // direct write to Port C
    ctx->portc = v;
    if (ctx->fdc_enabled) juku_fdc_portc(&ctx->fdc, ctx->portc);
    juku_set_mode(ctx, ctx->portc & 0b11);
  } else if (p == 0x07) {          // 8255 control port
    if (v & 0x80) {                // mode-set command: outputs reset to 0
      ctx->portc = 0;
      if (ctx->fdc_enabled) juku_fdc_portc(&ctx->fdc, ctx->portc);
      juku_set_mode(ctx, 0);
    } else {                       // bit set/reset on Port C
      int bit = (v >> 1) & 7;
      if (v & 1) ctx->portc |= (1u << bit); else ctx->portc &= ~(1u << bit);
      if (ctx->fdc_enabled) juku_fdc_portc(&ctx->fdc, ctx->portc);
      juku_set_mode(ctx, ctx->portc & 0b11);
    }
  }
}

static uint8_t cpu_read(void *p, uint16_t a) { juku *ctx = p; return juku_rb(ctx, &ctx->cpu, a); }
static void cpu_write(void *p, uint16_t a, uint8_t v) { juku *ctx = p; juku_wb(ctx, &ctx->cpu, a, v); }
static uint8_t cpu_in(void *p, uint8_t a) { juku *ctx = p; return juku_pin(ctx, &ctx->cpu, a); }
static void cpu_out(void *p, uint8_t a, uint8_t v) { juku *ctx = p; juku_pout(ctx, &ctx->cpu, a, v); }

juku *juku_create(void) {
  juku *ctx = calloc(1, sizeof(*ctx));
  if (!ctx) return NULL;
  ctx->mode = 0;
  ctx->portc = 0;
  ctx->video_stride = 40;
  ctx->video_lines = 241;
  ctx->video_modx_sequence = 0;
  ctx->video_stock_sequence = 0;
  ctx->video_64_sequence = 0;
  ctx->video_modx_mode = 0;
  ctx->video_console_mode = 0;
  ctx->kbd_s21_config = 0;
  ctx->fdc_enabled = 0;
  ctx->fdc_bus_invert = 0;
  ctx->cart_enabled = 0;
  ctx->rom_consecutive_a12_low = 0;
  ctx->rom_read_burst_count = 0;
  ctx->cpu_a12_increment_fault = 0;
  ctx->cpu_a12_increment_fault_arm_enabled = 0;
  ctx->cpu_a12_increment_fault_arm_fired = 0;
  ctx->cpu_a12_increment_fault_arm_pc = 0;
  ctx->cpu_a12_increment_fault_arm_bank_mode = -1;
  ctx->cpu_a12_increment_fault_disarm_enabled = 0;
  ctx->cpu_a12_increment_fault_disarm_fired = 0;
  ctx->cpu_a12_increment_fault_disarm_pc = 0;
  ctx->exec_byte_fault_enabled = 0;
  ctx->exec_byte_fault_addr = 0;
  ctx->exec_byte_fault_value = 0;
  ctx->timing_log = 0;
  ctx->io_trace = 0;
  ctx->bank_trace = 1;
  ctx->watch_address = -1;
  ctx->watch_address_end = -1;
  ctx->watch_write_count = 0;
  ctx->watch_write_previous_address = 0;
  ctx->watch_write_previous_value = 0;
  ctx->watch_write_previous_pc = 0;
  ctx->watch_write_previous_cycle = 0;
  ctx->watch_write_last_address = 0;
  ctx->watch_write_last_value = 0;
  ctx->watch_write_last_pc = 0;
  ctx->watch_write_last_cycle = 0;
  ctx->ram_fault_enabled = 0;
  ctx->ram_fault_addr = 0;
  ctx->ram_fault_stuck_low = 0;
  ctx->ram_fault_stuck_high = 0;
  ctx->ram_fault_all = 0;
  ctx->ram_drop_write_enabled = 0;
  ctx->ram_drop_write_addr = 0;
  ctx->ram_drop_write_value = 0;
  ctx->ram_drop_write_remaining = 0;
  ctx->ram_alias_enabled = 0;
  ctx->ram_alias_page_a = 0;
  ctx->ram_alias_page_b = 0;
  ctx->dram_retention_cycles = 0;
  ctx->dram_retention_armed = 1;
  ctx->dram_retention_arm_pc_enabled = 0;
  ctx->dram_retention_arm_pc = 0;
  ctx->dram_decay_count = 0;
  ctx->dram_coverage_count = 0;
  ctx->dram_coverage_start = 0;
  ctx->dram_full_coverage_reported = 0;
  ctx->pic_fault_enabled = 0;
  ctx->pic_fault_stuck_low = 0;
  ctx->pic_fault_stuck_high = 0;
  ctx->ppi_fault_enabled = 0;
  ctx->ppi_fault_port = 0;
  ctx->ppi_fault_stuck_low = 0;
  ctx->ppi_fault_stuck_high = 0;
  ctx->pit_fault_enabled = 0;
  ctx->pit_fault_port = 0;
  ctx->pit_fault_stuck_low = 0;
  ctx->pit_fault_stuck_high = 0;
  ctx->usart = (juku_usart){
  .expect_mode = 1,
  .transfer_cycles = 16,
  .byte_cycles = 256,
};
  ctx->usart_pit_clock = 0;
  ctx->usart_pit_cpu_hz = 0;
  ctx->usart_pit_divisor = 0;
  ctx->usart_pit_clock_valid = 1;
  ctx->usart_tx_irq_armed = 0;
  ctx->usart_tx_irq_level = 0;
  ctx->usart_rx_irq_level = 0;
  ctx->usart_tx_irq_pending = 0;
  ctx->usart_rx_irq_pending = 0;
  ctx->usart_host_sync_armed = 0;
  ctx->usart_host_sync_waiting = 0;
  ctx->usart_host_sync_ms = 0;
  ctx->g_vw = 0;
  ctx->g_vw_limit = 0;
  ctx->tpa_opcode_fetches = 0;
  ctx->tpa_z80_prefix_fetches = 0;
  ctx->tpa_undocumented_opcode_fetches = 0;
  ctx->checkpoint_generation = 0;
  ctx->tpa_program_starts = 0;
  ctx->tpa_program_entry_sp = 0;
  ctx->tpa_program_stack_anchor_sp = 0;
  ctx->tpa_program_stack_low_sp = 0;
  ctx->tpa_program_current_stack_anchor_sp = 0;
  ctx->tpa_program_segment_min_anchor_sp = 0;
  ctx->tpa_program_segment_max_anchor_sp = 0;
  ctx->tpa_program_stack_segments = 0;
  ctx->tpa_program_stack_bytes = 0;
  ctx->tpa_program_explicit_sp_writes = 0;
  ctx->tpa_program_call_depth = 0;
  ctx->tpa_program_bdos_return_pc = 0;
  ctx->tpa_program_in_bdos = 0;
  ctx->tpa_program_bdos_tail_call = 0;
  ctx->tpa_program_seen = 0;
  ctx->tpa_measurement_generation = 0;
  ctx->tpa_measurement_controlled = 0;
  ctx->tpa_measurement_armed = 0;
  ctx->tpa_measurement_frozen = 0;
  ctx->pic_icw1 = 0;
  ctx->pic_icw2 = 0;
  ctx->pic_mask = 0xFF;
  ctx->pic_expect_icw2 = 0;
  ctx->usart_rx_irq_count = 0;
  ctx->usart_tx_irq_count = 0;
  ctx->frame_irq_count = 0;
  ctx->console_len = 0;
  ctx->console_visible_len = 0;
  ctx->kbd_str = 0;
  ctx->kbd_pos = 0;
  ctx->kbd_phase = 0;
  ctx->kbd_enabled = 0;
  ctx->kbd_col = 0;
  ctx->kbd_start_vram = 42000;
  ctx->kbd_hold_frames = 3;
  ctx->kbd_gap_frames = 3;
  ctx->kbd_trace = 0;
  ctx->kbd_pc_trigger_enabled = 0;
  ctx->kbd_pc_trigger_fired = 0;
  ctx->kbd_pc_trigger_active = 0;
  ctx->kbd_pc_trigger_hold_frames = 0;
  ctx->kbd_pc_trigger_pc = 0;
  ctx->kbd_pc_trigger_char = 0;
  ctx->kbd_pc_trigger_gate_enabled = 0;
  ctx->kbd_pc_trigger_gate_address = 0;
  ctx->kbd_pc_trigger_gate_value = 0;
  i8080_init(&ctx->cpu);
  ctx->cpu.userdata = ctx;
  ctx->cpu.read_byte = cpu_read; ctx->cpu.write_byte = cpu_write;
  ctx->cpu.port_in = cpu_in; ctx->cpu.port_out = cpu_out;
  juku_pit_init(ctx);
  return ctx;
}
void juku_destroy(juku *ctx) { free(ctx); }
int juku_load_rom(juku *ctx, const void *bytes, size_t size) {
  if (!ctx || !bytes || !size || size > ROM_SIZE) return -EINVAL;
  if (ctx->cpu.cyc) return -EBUSY;
  memset(ctx->rom, 0, sizeof(ctx->rom));
  memcpy(ctx->rom, bytes, size);
  return 0;
}
const uint8_t *juku_video(juku *ctx, unsigned *stride, unsigned *lines) {
  if (!ctx) return NULL;
  if (stride) *stride = ctx->video_stride;
  if (lines) *lines = ctx->video_lines;
  return ctx->ram + VRAM_BASE;
}
void juku_step_cpu(juku *ctx) { i8080_step(&ctx->cpu); }
void juku_step_devices(juku *ctx) {
    juku_sync_fdc_time(ctx, &ctx->cpu);
    juku_usart_poll(ctx, ctx->cpu.cyc);
    // D11 RxRDY and TxRDY directly drive D10/PIC IR2 and IR3.  NetBios is
    // interrupt-driven, so status-register emulation alone cannot put its
    // queued request onto the wire.
    if (ctx->usart_rx_irq_pending &&
        ctx->usart.fault_rx_irq_delay_once_enabled &&
        !ctx->usart.fault_rx_irq_delay_once_fired &&
        ctx->usart.rx_bytes >= ctx->usart.fault_rx_irq_delay_once_after) {
      ctx->usart.fault_rx_irq_delay_once_fired = 1;
      ctx->usart.fault_rx_irq_delay_until =
          ctx->cpu.cyc + ctx->usart.fault_rx_irq_delay_cycles;
      juku_log(ctx, "[USART] delaying one RxRDY IRQ after byte=%lu until cyc=%lu\n",
              ctx->usart.rx_bytes, ctx->usart.fault_rx_irq_delay_until);
    }
    if (ctx->usart_rx_irq_pending &&
        (!ctx->usart.fault_rx_irq_delay_once_fired ||
         ctx->cpu.cyc >= ctx->usart.fault_rx_irq_delay_until) &&
        juku_take_pic_irq(ctx, &ctx->cpu, 2, "USART RxRDY", &ctx->usart_rx_irq_count))
      ctx->usart_rx_irq_pending = 0;
    if (ctx->usart_tx_irq_pending &&
        juku_take_pic_irq(ctx, &ctx->cpu, 3, "USART TxRDY", &ctx->usart_tx_irq_count))
      ctx->usart_tx_irq_pending = 0;
    // --- frame interrupt: 8253 VER-RTR -> 8259 IR5 -> CPU (MCS-80 CALL to the ICW vector) ---
    if (ctx->frame_cyc && ctx->cpu.cyc >= ctx->next_frame) {
      ctx->next_frame += ctx->frame_cyc;
      // A host PTY byte represents a physical contact. Publish newly queued
      // contacts only at a frame boundary so they cannot appear halfway
      // through one guest matrix sweep. Scripted JUKU_KEYS are unchanged.
      if (ctx->kbd_str == ctx->console_queue) ctx->console_visible_len = ctx->console_len;
      int frame_taken = juku_take_pic_irq(ctx, &ctx->cpu, 5, "frame", &ctx->frame_irq_count);
      char frame_key = juku_kbd_current_char(ctx);
      if (ctx->kbd_trace && frame_key)
        juku_log(ctx, "[KBD] frame char=%02X pos=%d phase=%d irq=%s iff=%d mask=%02X "
                "pc=%04X cyc=%lu g_vw=%lu\n",
                (unsigned char)frame_key, ctx->kbd_pos, ctx->kbd_phase,
                frame_taken ? "taken" : "blocked", ctx->cpu.iff, ctx->pic_mask,
                ctx->cpu.pc, ctx->cpu.cyc, ctx->g_vw);
      // Scripted key contacts follow physical frame time. They may be sampled
      // either by the monitor's frame ISR or by a RAM-resident polling BIOS;
      // PIC masking must not freeze a real key contact in time.
      if (frame_key && ctx->g_vw >= ctx->kbd_start_vram) {
        int hold_frames = ctx->kbd_pc_trigger_active
                          ? ctx->kbd_pc_trigger_hold_frames : ctx->kbd_hold_frames;
        if (frame_key == '|') {
          if (juku_ekdos_prompt_visible(ctx)) {
            juku_log(ctx, "[KBD] prompt wait marker consumed at g_vw=%lu cyc=%lu pos=%d\n",
                    ctx->g_vw, ctx->cpu.cyc, ctx->kbd_pos);
            ctx->kbd_phase = 0;
            ctx->kbd_pos++;
          }
        } else if (++ctx->kbd_phase >= hold_frames + ctx->kbd_gap_frames) {
          ctx->kbd_phase = 0;
          if (ctx->kbd_pc_trigger_active)
            ctx->kbd_pc_trigger_active = 0;
          else
            ctx->kbd_pos++;
        }
      }

      if (ctx->hooks.frame) ctx->hooks.frame(ctx->hooks.user, ctx->cpu.cyc);
    }

}
void juku_step(juku *ctx) { juku_step_cpu(ctx); juku_step_devices(ctx); }
unsigned long juku_run(juku *ctx, unsigned long budget) {
  unsigned long start = ctx->cpu.cyc;
  while (ctx->cpu.cyc - start < budget && (!ctx->cpu.halted || ctx->frame_cyc)) {
    unsigned long before = ctx->cpu.cyc;
    juku_step(ctx);
    if (ctx->cpu.cyc == before) break;
  }
  return ctx->cpu.cyc - start;
}
