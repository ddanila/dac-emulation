/* Bounded asynchronous receive path for the keyboard-connected SIO A.
 * WR3/WR4 select enable, width, parity and clock divisor; FIFO is three bytes.
 * Channel A TX drives printer capture; channel B is the V.24 terminal.
 * Synchronous modes remain unimplemented. */
#include "robotron.h"
#include <string.h>
unsigned robotron_printer_cts(robotron *m) {
  return m->printer_ext_latched ? m->printer_cts_latched : !m->printer_state;
}
void robotron_printer_state(robotron *m, unsigned state) {
  if (state > 3)
    return;
  unsigned previous = !m->printer_state;
  m->printer_state = state;
  if (previous != !state && (m->sio_regs[0][1] & 1) &&
      !m->printer_ext_latched) {
    m->printer_ext_pending = m->printer_ext_latched = 1;
    m->printer_cts_latched = !state;
  }
}
static void break_status(robotron *m, unsigned active) {
  if (m->v24.break_active == active)
    return;
  m->v24.break_active = active;
  if ((m->sio_regs[1][1] & 1) && !m->v24.ext_latched) {
    m->v24.ext_latched = m->v24.ext_pending = 1;
    m->v24.ext_signals = m->v24.signals;
    m->v24.break_latched = active;
  }
}
static void receive_clock(robotron *m, unsigned ch, unsigned level) {
  robotron_sio_rx *s = ch ? &m->rx_b : &m->rx;
  uint8_t *r = m->sio_regs[ch];
  if (ch && (r[3] & 32) && !(m->v24.signals & 2)) {
    s->phase = 0;
    return;
  }
  if (!(r[3] & 1) || !(r[4] & 12)) {
    s->phase = 0;
    return;
  }
  const unsigned divisors[] = {1, 16, 32, 64}, widths[] = {5, 7, 6, 8};
  unsigned div = divisors[r[4] >> 6];
  if (ch && m->v24.break_active) {
    if (level) {
      break_status(m, 0);
      s->phase = 0;
    } else
      return;
  }
  if (!s->phase) {
    if (!level) {
      s->phase = div == 1 ? 2 : 1;
      s->wait = div == 1 ? 1 : div / 2;
      s->bits = s->byte = s->parity = 0;
      if (ch)
        m->v24.frame_errors = 0;
    }
    return;
  }
  if (--s->wait)
    return;
  s->wait = div;
  if (s->phase == 1) {
    s->phase = level ? 0 : 2;
    return;
  }
  if (s->phase == 2) {
    s->byte |= level << s->bits++;
    s->parity ^= level;
    if (s->bits == widths[r[3] >> 6])
      s->phase = (r[4] & 1) ? 3 : 4;
  } else if (s->phase == 3) {
    if ((s->parity ^ level) != !(r[4] & 2))
      s->errors |= 0x10;
    s->phase = 4;
  } else {
    if (!level) {
      if (ch)
        m->v24.frame_errors |= 0x40;
      else
        s->errors |= 0x40;
    }
    if (ch && !level && !s->byte)
      break_status(m, 1);
    if (s->count == 3) {
      s->errors |= 0x20;
      if (ch) {
        unsigned tail = (s->read + 2) % 3;
        s->fifo[tail] = s->byte;
        m->v24.fifo_errors[tail] = m->v24.frame_errors;
      }
    } else {
      s->fifo[(s->read + s->count) % 3] = s->byte;
      if (ch)
        m->v24.fifo_errors[(s->read + s->count) % 3] = m->v24.frame_errors;
      s->count++;
    }
    s->phase = 0;
    m->serial_events++;
    if ((r[1] & 0x18) == 0x10 || (r[1] & 0x18) == 0x18 ||
        ((r[1] & 0x18) == 8 &&
         (s->first || (s->errors & 0x20) || (ch && m->v24.frame_errors)))) {
      s->pending = 1;
      s->first = 0;
    }
  }
}
void robotron_serial_clock(void *p, unsigned level) {
  receive_clock(p, 0, level);
}
void robotron_v24_receive_clock(robotron *m, unsigned level) {
  receive_clock(m, 1, level);
}
uint8_t robotron_sio_read(robotron *m, unsigned control) {
  robotron_sio_rx *s = &m->rx;
  if (!control) {
    if (!s->count)
      return 0;
    uint8_t v = s->fifo[s->read];
    s->read = (s->read + 1) % 3;
    s->count--;
    if (!s->count)
      s->pending = 0;
    else if (m->sio_regs[0][1] & 0x10)
      s->pending = 1;
    return v;
  }
  unsigned reg = m->sio_pointer[0];
  m->sio_pointer[0] = 0;
  if (reg == 1)
    return (!m->tx_full && !m->tx_clocks) | s->errors;
  if (reg == 2)
    return m->sio_regs[1][2];
  return (0x58 | (robotron_printer_cts(m) << 5) | (!m->tx_full << 2)) |
         !!s->count |
         ((s->pending || (m->tx_pending && (m->sio_regs[0][1] & 2)) ||
           (m->printer_ext_pending && (m->sio_regs[0][1] & 1)))
          << 1);
}
void robotron_sio_control(robotron *m, unsigned ch, uint8_t v) {
  unsigned reg = m->sio_pointer[ch];
  if (reg) {
    m->sio_regs[ch][reg] = v;
    m->sio_pointer[ch] = 0;
    if (reg == 3 && !(v & 1))
      (ch ? &m->rx_b : &m->rx)->phase = 0;
    return;
  }
  m->sio_pointer[ch] = v & 7;
  if (ch) {
    switch ((v >> 3) & 7) {
    case 2:
      m->v24.ext_pending = m->v24.ext_latched = 0;
      m->v24.ext_signals = m->v24.signals;
      m->v24.break_latched = m->v24.break_active;
      break;
    case 3:
      memset(&m->rx_b, 0, sizeof(m->rx_b));
      memset(m->sio_regs[1], 0, 8);
      m->rx_b.first = 1;
      m->v24.break_active = m->v24.break_latched = m->v24.rx_locked = 0;
      m->v24.ext_pending = m->v24.ext_service = m->v24.ext_latched = 0;
      memset(m->v24.fifo_errors, 0, 3);
      m->v24.full = m->v24.tx_clocks = m->v24.pending = m->v24.in_service = 0;
      break;
    case 4:
      m->rx_b.first = 1;
      break;
    case 5:
      m->v24.pending = 0;
      break;
    case 6:
      m->rx_b.errors = 0;
      if (m->v24.rx_locked && m->rx_b.count) {
        m->rx_b.read = (m->rx_b.read + 1) % 3;
        m->rx_b.count--;
        m->rx_b.pending = 0;
      }
      m->v24.rx_locked = 0;
      break;
    case 7:
      if (m->rx_b.in_service)
        m->rx_b.in_service = 0;
      else if (m->v24.in_service)
        m->v24.in_service = 0;
      else
        m->v24.ext_service = 0;
      break;
    default:
      break;
    }
    return;
  }
  switch ((v >> 3) & 7) {
  case 2:
    m->printer_ext_pending = m->printer_ext_latched = 0;
    break;
  case 3:
    m->printer_ext_pending = m->printer_ext_service = m->printer_ext_latched =
        0;
    memset(&m->rx, 0, sizeof(m->rx));
    memset(m->sio_regs[0], 0, 8);
    m->rx.first = 1;
    m->tx_full = m->tx_clocks = m->tx_pending = m->tx_in_service = 0;
    break;
  case 4:
    m->rx.first = 1;
    break;
  case 5:
    m->tx_pending = 0;
    break;
  case 6:
    m->rx.errors = 0;
    break;
  case 7:
    if (m->rx.in_service)
      m->rx.in_service = 0;
    else if (m->tx_in_service)
      m->tx_in_service = 0;
    else if (m->printer_ext_service)
      m->printer_ext_service = 0;
    else if (m->rx_b.in_service)
      m->rx_b.in_service = 0;
    else if (m->v24.in_service)
      m->v24.in_service = 0;
    else
      m->v24.ext_service = 0;
    break;
  default:
    break;
  }
}

/* One holding register plus a shift register. CTC0 channel 0 clocks TX A.
 * Capture bytes after the programmed asynchronous frame has been clocked.
 * CTS gates new characters when WR3 Auto Enables is set; in-flight frames
 * finish.
 */
void robotron_printer_clock(robotron *m) {
  const uint8_t *r = m->sio_regs[0];
  const unsigned div[] = {1, 16, 32, 64}, widths[] = {5, 7, 6, 8};
  if (!(r[5] & 8) || !(r[4] & 12))
    return;
  if (!m->tx_clocks && m->tx_full) {
    if ((r[3] & 32) && m->printer_state)
      return;
    m->printer_accept = !m->printer_state;
    unsigned bits = widths[(r[5] >> 5) & 3];
    m->tx_shift = m->tx_holding & ((1u << bits) - 1);
    m->tx_full = 0;
    if (r[1] & 2)
      m->tx_pending = 1;
    unsigned half = 2 * (1 + bits + (r[4] & 1)) + ((r[4] & 12) == 4   ? 2
                                                   : (r[4] & 12) == 8 ? 3
                                                                      : 4);
    m->tx_clocks = (half * div[r[4] >> 6] + 1) / 2;
  }
  if (m->tx_clocks && !--m->tx_clocks) {
    if (!m->printer_accept) {
      m->printer_dropped++;
      return;
    }
    if (m->printer_size < sizeof(m->printer))
      m->printer[m->printer_size++] = m->tx_shift;
    else
      m->printer_overflow = 1;
  }
}

/* Peer waveform is advanced on the CPU clock, independently of guest RX
 * sampling. Half-bit cells preserve 1.5 stop bits even with SIO x1 clocking.
 * peer_format: data bits 5..8 in low nibble, parity 0/1(odd)/2(even)
 * in bits 4..5, stop half-bits 2/3/4 in bits 8..10. Baud 0 follows guest. */
void robotron_v24_signals(robotron *m, unsigned value) {
  unsigned changed = (m->v24.signals ^ value) & 3;
  m->v24.signals = value;
  if (changed && (m->sio_regs[1][1] & 1) && !m->v24.ext_latched) {
    m->v24.ext_signals = value;
    m->v24.break_latched = m->v24.break_active;
    m->v24.ext_latched = 1;
    m->v24.ext_pending = 1;
  }
}
/* Independent peer samples the outgoing UART waveform. Adaptive mode uses
 * guest divisors; fixed mode has its own 16x oscillator in CPU-clock time. */
static void peer_receive(robotron *m, unsigned div) {
  robotron_sio_rx *s = &m->v24.decoder;
  unsigned format = m->v24.peer_format;
  const uint8_t *r = m->sio_regs[1];
  const unsigned widths[] = {5, 7, 6, 8};
  unsigned width = m->v24.peer_baud ? (format & 15) : widths[(r[5] >> 5) & 3];
  unsigned parity = m->v24.peer_baud ? ((format >> 4) & 3)
                                     : ((r[4] & 1) ? ((r[4] & 2) ? 2 : 1) : 0);
  unsigned level =
      (r[5] & 16) ? 0
      : m->v24.tx_clocks
          ? ((m->v24.tx_frame >>
              (m->v24.tx_elapsed / (m->v24.tx_div ? m->v24.tx_div : 1))) &
             1)
          : 1;
  if (!s->phase) {
    if (!level) {
      s->phase = div == 1 ? 2 : 1;
      s->wait = div == 1 ? 1 : div / 2;
      s->byte = s->bits = s->parity = 0;
    }
    return;
  }
  if (--s->wait)
    return;
  s->wait = div;
  if (s->phase == 1) {
    s->phase = level ? 0 : 2;
    return;
  }
  if (s->phase == 2) {
    s->byte |= level << s->bits++;
    s->parity ^= level;
    if (s->bits == width)
      s->phase = parity ? 3 : 4;
    return;
  }
  if (s->phase == 3) {
    if ((s->parity ^ level) != (parity == 1))
      s->errors |= 16;
    s->phase = 4;
    return;
  }
  if (!level)
    s->errors |= 64;
  if (m->v24.decoded_size < 65536)
    m->v24.decoded[m->v24.decoded_size++] = s->byte;
  else
    m->v24.decoded_overflow = 1;
  s->phase = 0;
}
void robotron_v24_peer_tick(robotron *m) {
  const uint8_t *r = m->sio_regs[1];
  const unsigned widths[] = {5, 7, 6, 8}, divisors[] = {1, 16, 32, 64};
  robotron_timer *t = &m->ctc[5];
  unsigned baud = m->v24.peer_baud;
  if (baud) {
    m->v24.decode_phase += 16 * baud;
    while (m->v24.decode_phase >= 3993600) {
      m->v24.decode_phase -= 3993600;
      peer_receive(m, 16);
    }
  }
  if (!baud &&
      (!(r[4] & 12) || (t->control & 0x42) || t->waiting || !t->counter))
    return;
  if (!m->v24.bits && m->v24.count && (m->v24.signals & 2) &&
      (!(m->v24.signals & 4) || (r[5] & 2))) {
    unsigned width = baud ? (m->v24.peer_format & 15) : widths[r[3] >> 6];
    unsigned parity = baud ? ((m->v24.peer_format >> 4) & 3)
                           : ((r[4] & 1) ? ((r[4] & 2) ? 2 : 1) : 0);
    unsigned stop = baud ? ((m->v24.peer_format >> 8) & 7)
                         : ((r[4] & 12) == 4   ? 2
                            : (r[4] & 12) == 8 ? 3
                                               : 4);
    unsigned byte = m->v24.input[m->v24.read], p = 0, frame = 0, halves = 2;
    m->v24.read = (m->v24.read + 1) % 65536;
    m->v24.count--;
    for (unsigned i = 0; i < width; i++) {
      unsigned bit = (byte >> i) & 1;
      p ^= bit;
      frame |= (bit ? 3u : 0u) << halves;
      halves += 2;
    }
    if (parity) {
      frame |= ((p ^ (parity == 1)) ? 3u : 0u) << halves;
      halves += 2;
    }
    frame |= ((1u << stop) - 1) << halves;
    halves += stop;
    m->v24.frame = frame;
    m->v24.bits = halves;
    m->v24.peer_phase = 0;
  }
  if (!m->v24.bits)
    return;
  unsigned threshold =
      baud ? 3993600u
           : ((t->constant ? t->constant : 256) *
              ((t->control & 32) ? 256 : 16) * divisors[r[4] >> 6] / 2);
  m->v24.peer_phase += baud ? 2 * baud : 1;
  while (m->v24.bits && m->v24.peer_phase >= threshold) {
    m->v24.peer_phase -= threshold;
    m->v24.frame >>= 1;
    m->v24.bits--;
  }
}
/* One falling TX clock edge; independent from RX clock sampling. */
void robotron_v24_transmit_clock(robotron *m) {
  const uint8_t *r = m->sio_regs[1];
  const unsigned divisors[] = {1, 16, 32, 64}, widths[] = {5, 7, 6, 8};
  unsigned div = divisors[r[4] >> 6];
  if (!(r[4] & 12))
    return;
  if (!m->v24.tx_clocks &&
      (!(r[5] & 8) || ((r[3] & 32) && !(m->v24.signals & 1))))
    return;
  if (!m->v24.tx_clocks && m->v24.full) {
    unsigned width = widths[(r[5] >> 5) & 3];
    m->v24.shift = m->v24.holding & ((1u << width) - 1);
    m->v24.full = 0;
    if (r[1] & 2)
      m->v24.pending = 1;
    unsigned half = 2 * (1 + width + (r[4] & 1)) + ((r[4] & 12) == 4   ? 2
                                                    : (r[4] & 12) == 8 ? 3
                                                                       : 4);
    m->v24.tx_clocks = (half * div + 1) / 2;
    unsigned p = 0;
    for (unsigned i = 0; i < width; i++)
      p ^= (m->v24.shift >> i) & 1;
    m->v24.tx_frame = (unsigned)m->v24.shift << 1;
    unsigned end = 1 + width;
    if (r[4] & 1)
      m->v24.tx_frame |= (p ^ !(r[4] & 2)) << end++;
    m->v24.tx_frame |= 3u << end;
    m->v24.tx_elapsed = 0;
    m->v24.tx_div = div;
  }
  if (!m->v24.peer_baud)
    peer_receive(m, div);
  if (m->v24.tx_clocks)
    m->v24.tx_elapsed++;
  if (m->v24.tx_clocks && !--m->v24.tx_clocks && (m->v24.signals & 2)) {
    m->serial_events++;
    if (m->v24.size < sizeof(m->v24.output))
      m->v24.output[m->v24.size++] = m->v24.shift;
    else
      m->v24.overflow = 1;
  }
}
/* The museum board route supplies both clocks from CTC0 channel 1.
 * Native fixtures may supply RX samples and TX edges independently. */
void robotron_v24_clock(robotron *m) {
  if (!(m->sio_regs[1][4] & 12))
    return;
  robotron_v24_receive_clock(
      m, m->v24.bits && (m->v24.signals & 2) ? (m->v24.frame & 1) : 1);
  robotron_v24_transmit_clock(m);
}
uint8_t robotron_v24_read(robotron *m, unsigned control) {
  robotron_sio_rx *s = &m->rx_b;
  if (!control) {
    if (!s->count)
      return 0;
    uint8_t v = s->fifo[s->read];
    if ((m->sio_regs[1][1] & 0x18) == 8 &&
        ((s->errors & 0x20) || m->v24.fifo_errors[s->read])) {
      m->v24.rx_locked = 1;
      s->pending = 1;
      return v;
    }
    s->read = (s->read + 1) % 3;
    s->count--;
    if (!s->count)
      s->pending = 0;
    else if (m->sio_regs[1][1] & 16)
      s->pending = 1;
    return v;
  }
  unsigned reg = m->sio_pointer[1];
  m->sio_pointer[1] = 0;
  if (reg == 1)
    return (!m->v24.full && !m->v24.tx_clocks) | s->errors |
           (s->count ? m->v24.fifo_errors[s->read] : 0);
  if (reg == 2) {
    unsigned code =
        m->rx.pending            ? 12
        : m->tx_pending          ? 8
        : m->printer_ext_pending ? 10
        : s->pending
            ? ((s->errors | (s->count ? m->v24.fifo_errors[s->read] : 0)) & 0x70
                   ? 6
                   : 4)
        : m->v24.pending ? 0
                         : 2;
    return (m->sio_regs[1][1] & 4) ? (m->sio_regs[1][2] & 0xf1) | code
                                   : m->sio_regs[1][2];
  }
  unsigned signals = m->v24.ext_latched ? m->v24.ext_signals : m->v24.signals;
  return ((m->v24.ext_latched ? m->v24.break_latched : m->v24.break_active)
              ? 0x80
              : 0) |
         0x40 | ((signals & 1) ? 0x20 : 0) | ((signals & 2) ? 8 : 0) |
         (!m->v24.full << 2) | !!s->count;
}
