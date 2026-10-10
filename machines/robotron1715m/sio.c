/* Bounded asynchronous receive path for the keyboard-connected SIO A.
 * WR3/WR4 select enable, width, parity and clock divisor; FIFO is three bytes.
 * Channel A TX clocks drive a bounded printer capture; other channels and
 * synchronous modes remain unimplemented. */
#include "robotron.h"
#include <string.h>
void robotron_serial_clock(void *p, unsigned level) {
  robotron *m = p;
  robotron_sio_rx *s = &m->rx;
  uint8_t *r = m->sio_regs[0];
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
  return (0x78 | (!m->tx_full << 2)) | !!s->count;
}
void robotron_sio_control(robotron *m, unsigned ch, uint8_t v) {
  unsigned reg = m->sio_pointer[ch];
  if (reg) {
    m->sio_regs[ch][reg] = v;
    m->sio_pointer[ch] = 0;
    if (!ch && reg == 3 && !(v & 1))
      m->rx.phase = 0;
    return;
  }
  m->sio_pointer[ch] = v & 7;
  if (ch)
    return;
  switch ((v >> 3) & 7) {
  case 3:
    memset(&m->rx, 0, sizeof(m->rx));
    memset(m->sio_regs[0], 0, 8);
    m->rx.first = 1;
    m->tx_full = m->tx_clocks = 0;
    break;
  case 4:
    m->rx.first = 1;
    break;
  case 6:
    m->rx.errors = 0;
    break;
  case 7:
    m->rx.in_service = 0;
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
