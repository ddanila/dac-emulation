/* Bounded asynchronous receive path for the keyboard-connected SIO A.
 * WR3/WR4 select enable, width, parity and clock divisor; FIFO is three bytes.
 * Other serial channels, synchronous modes and TX remain unimplemented. */
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
    return 1 | s->errors;
  if (reg == 2)
    return m->sio_regs[1][2];
  return 0x7c | !!s->count;
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
