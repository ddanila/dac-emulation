/* Bounded asynchronous receive path for the keyboard-connected SIO A.
 * WR3/WR4 select enable, width, parity and clock divisor; FIFO is three bytes.
 * Channel A TX drives printer capture; channel B is the V.24 terminal.
 * Synchronous modes and external-status interrupt latching remain
 * unimplemented. */
#include "robotron.h"
#include <string.h>
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
  if (!s->phase) {
    if (!level) {
      s->phase = div == 1 ? 2 : 1;
      s->wait = div == 1 ? 1 : div / 2;
      s->bits = s->byte = s->parity = 0;
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
    if (!level)
      s->errors |= 0x40;
    if (s->count == 3)
      s->errors |= 0x20;
    else {
      s->fifo[(s->read + s->count) % 3] = s->byte;
      s->count++;
    }
    s->phase = 0;
    if ((r[1] & 0x18) == 0x10 || (r[1] & 0x18) == 0x18 ||
        ((r[1] & 0x18) == 8 && s->first)) {
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
  return (0x78 | (!m->tx_full << 2)) | !!s->count |
         ((s->pending || (m->tx_pending && (m->sio_regs[0][1] & 2))) << 1);
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
    case 3:
      memset(&m->rx_b, 0, sizeof(m->rx_b));
      memset(m->sio_regs[1], 0, 8);
      m->rx_b.first = 1;
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
      break;
    case 7:
      if (m->rx_b.in_service)
        m->rx_b.in_service = 0;
      else
        m->v24.in_service = 0;
      break;
    default:
      break;
    }
    return;
  }
  switch ((v >> 3) & 7) {
  case 3:
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
    else
      m->tx_in_service = 0;
    break;
  default:
    break;
  }
}

/* One holding register plus a shift register. CTC0 channel 0 clocks TX A.
 * Capture bytes after the programmed asynchronous frame has been clocked.
 * This virtual printer is always ready; no physical waveform/handshake claim.
 */
void robotron_printer_clock(robotron *m) {
  const uint8_t *r = m->sio_regs[0];
  const unsigned div[] = {1, 16, 32, 64}, widths[] = {5, 7, 6, 8};
  if (!(r[5] & 8) || !(r[4] & 12))
    return;
  if (!m->tx_clocks && m->tx_full) {
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
    if (m->printer_size < sizeof(m->printer))
      m->printer[m->printer_size++] = m->tx_shift;
    else
      m->printer_overflow = 1;
  }
}

/* W/M reference internal-clock route: CTC0 ZC/TO1 through the S1 clock
 * selection, sheet Stromlaufplan D. The virtual peer shares this clock and
 * follows WR3/WR4 framing. External-clock switch positions are not modeled. */
void robotron_v24_clock(robotron *m) {
  const uint8_t *r = m->sio_regs[1];
  const unsigned divisors[] = {1, 16, 32, 64}, widths[] = {5, 7, 6, 8};
  unsigned div = divisors[r[4] >> 6];
  if (!(r[4] & 12))
    return;
  if (!m->v24.bits && m->v24.count && (m->v24.signals & 2) &&
      (!(m->v24.signals & 4) || (r[5] & 2))) {
    unsigned byte = m->v24.input[m->v24.read], width = widths[r[3] >> 6],
             parity = 0;
    m->v24.read = (m->v24.read + 1) % 65536;
    m->v24.count--;
    byte &= (1u << width) - 1;
    m->v24.frame = byte << 1;
    m->v24.bits = 1 + width;
    if (r[4] & 1) {
      for (unsigned i = 0; i < width; i++)
        parity ^= (byte >> i) & 1;
      m->v24.frame |= (parity ^ !(r[4] & 2)) << m->v24.bits++;
    }
    /* Round 1.5 stop bits to two in the adaptive peer; never shorten them. */
    unsigned stops = (r[4] & 12) == 4 ? 1 : 2;
    m->v24.frame |= ((1u << stops) - 1) << m->v24.bits;
    m->v24.bits += stops;
    m->v24.clocks = div;
  }
  robotron_v24_receive_clock(m, m->v24.bits ? (m->v24.frame & 1) : 1);
  if (m->v24.bits && !--m->v24.clocks) {
    m->v24.frame >>= 1;
    m->v24.bits--;
    m->v24.clocks = div;
  }
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
  }
  if (m->v24.tx_clocks && !--m->v24.tx_clocks && (m->v24.signals & 2)) {
    if (m->v24.size < sizeof(m->v24.output))
      m->v24.output[m->v24.size++] = m->v24.shift;
    else
      m->v24.overflow = 1;
  }
}
uint8_t robotron_v24_read(robotron *m, unsigned control) {
  robotron_sio_rx *s = &m->rx_b;
  if (!control) {
    if (!s->count)
      return 0;
    uint8_t v = s->fifo[s->read];
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
    return (!m->v24.full && !m->v24.tx_clocks) | s->errors;
  if (reg == 2) {
    unsigned code = m->rx.pending ? 12 : m->tx_pending ? 8 : s->pending ? 4 : 0;
    return (m->sio_regs[1][1] & 4) ? (m->sio_regs[1][2] & 0xf1) | code
                                   : m->sio_regs[1][2];
  }
  return 0x40 | ((m->v24.signals & 1) ? 0x20 : 0) |
         ((m->v24.signals & 2) ? 8 : 0) | (!m->v24.full << 2) | !!s->count;
}
