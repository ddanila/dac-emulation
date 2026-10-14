/* Functional model informed by the BSD-3-Clause MAME rt1715 driver and
 * Maxim Usov's MIT Robotron FPGA development models. See NOTICE/provenance.
 * No guest addresses are patched and no guest instructions are intercepted. */
#include "robotron.h"
#include <errno.h>
#include <string.h>
static int bank(robotron *m, unsigned b, uint16_t a) {
  if (!b)
    return a < 0x4000 ? 4 + (a >> 12) : 0;
  unsigned bits = m->prom[128 + (b << 4) + (a >> 12)] ^ 15;
  switch (bits) {
  case 1:
    return 0;
  case 2:
    return 1;
  case 4:
    return 2;
  case 8:
    return 3;
  default:
    return 5;
  }
}
uint8_t robotron_read(void *p, uint16_t a) {
  robotron *m = p;
  int b = bank(m, m->bank & 7, a);
  if (b < 4)
    return m->ram[b * 65536 + a];
  if (b == 4)
    return m->rom[a & 2047];
  if (b == 6)
    return m->chargen[a & 4095];
  if (b == 7)
    return m->vram[a & 4095];
  return 0;
}
void robotron_write(void *p, uint16_t a, uint8_t v) {
  robotron *m = p;
  int b = bank(m, (m->bank >> 4) & 7, a);
  if (b < 4)
    m->ram[b * 65536 + a] = v;
  else if (b == 6)
    m->chargen[a & 4095] = v;
  else if (b == 7) {
    m->vram[a & 4095] = v;
    m->video_writes++;
  }
}
unsigned robotron_drive_ready(const robotron *m, unsigned u) {
  return u < 2 && !m->drive[u].door_open && !m->drive[u].ejected && !(m->motor & (u ? 8 : 128)) && m->drive[u].ready &&
         (u ? m->disk_b.storage.read != NULL : m->disk.storage.read != NULL);
}
unsigned robotron_head_position(const robotron *m, unsigned u) {
  if (u > 1)
    return 0;
  const robotron_drive *d = &m->drive[u];
  unsigned target = m->fdc.physical[u] * 65536u;
  uint64_t age = m->cpu.cycles - d->step_at;
  if (age >= ROBOTRON_STEP_TICKS)
    return target;
  return (unsigned)((int64_t)d->from_q16 + ((int64_t)target - d->from_q16) *
                                               (int64_t)age /
                                               ROBOTRON_STEP_TICKS);
}
static void mechanics_tick(robotron *m) {
  for (unsigned u = 0; u < 2; u++) {
    robotron_drive *d = &m->drive[u];
    unsigned on = !(m->motor & (u ? 8 : 128));
    if (on && d->speed < ROBOTRON_SPINUP_TICKS)
      d->speed++;
    if (!on && d->speed)
      d->speed--; /* Explicit reference coast profile. */
    if (!on || d->door_open || d->ejected) {
      d->ready = d->ready_indexes = 0;
      d->loaded = 0;
    }
    d->fraction += d->speed;
    if (d->fraction >= ROBOTRON_SPINUP_TICKS) {
      d->fraction -= ROBOTRON_SPINUP_TICKS;
      if (++m->rotation[u] == ROBOTRON_REVOLUTION_TICKS) {
        m->rotation[u] = 0;
        unsigned inserted =
            !d->door_open && !d->ejected && !!(u ? m->disk_b.storage.read : m->disk.storage.read);
        if (inserted)
          d->index_count++;
        uint64_t interval = m->cpu.cycles - d->last_index;
        if (on && inserted && d->speed >= ROBOTRON_SPINUP_TICKS / 2) {
          if (d->ready_indexes < 2)
            d->ready_indexes++;
          d->ready = d->ready_indexes >= 2 &&
                     interval >= ROBOTRON_REVOLUTION_TICKS * 94u / 100 &&
                     interval <= ROBOTRON_REVOLUTION_TICKS * 106u / 100;
        }
        d->last_index = m->cpu.cycles;
      }
    }
    if (d->loaded && d->unload_at && m->cpu.cycles >= d->unload_at &&
        !(m->fdc.phase == 2 && m->fdc.unit == u))
      d->loaded = 0;
  }
}
static void result(robotron *m, unsigned len) {
  if (m->fdc.unit < 2)
    m->drive[m->fdc.unit].unload_at =
        m->cpu.cycles +
        (m->fdc.head_unload_ticks ? m->fdc.head_unload_ticks : 1022362);
  m->fdc.phase = 1;
  m->fdc.result_pos = 0;
  m->fdc.result_len = len;
}
static void finish(robotron *m, uint8_t st1) {
  robotron_fdc *f = &m->fdc;
  uint8_t r[] = {(uint8_t)((f->unit | (f->head << 2)) | (st1 ? 0x40 : 0)),
                 st1,
                 0,
                 (uint8_t)f->result_c,
                 (uint8_t)f->id_head,
                 (uint8_t)f->sector,
                 (uint8_t)f->n};
  if (f->scan_mode)
    r[2] = (f->scan_mode == 17 ? f->scan_compare == 0
                               : (f->scan_mode == 25 ? f->scan_compare <= 0
                                                     : f->scan_compare >= 0))
               ? 8
               : 4;
  r[2] |= f->error2;
  if (f->error2)
    r[0] |= 0x40;
  memcpy(f->result, r, 7);
  result(m, 7);
}
static dac_media *media(robotron *m) {
  return m->fdc.unit == 0 ? &m->disk : m->fdc.unit == 1 ? &m->disk_b : NULL;
}
static robotron_track *track(robotron *m) {
  robotron_fdc *f = &m->fdc;
  return f->unit < 2 && f->physical[f->unit] < 80 && f->head < 2
             ? &m->tracks[f->unit][f->physical[f->unit] * 2 + f->head]
             : NULL;
}
/* Preserve bytes already written when power/motor interrupts a data field.
 * DSK can retain the resulting bad CRC; raw images cannot store that metadata.
 */
void robotron_flush_interrupted_write(robotron *m) {
  robotron_fdc *f = &m->fdc;
  robotron_track *tr = track(m);
  if (f->phase != 2 || f->write != 1 || f->formatting ||
      (f->search && f->search != 5) || !f->data_pos || !tr ||
      f->slot >= tr->count || !media(m)->writable)
    return;
  robotron_sector *id = &tr->sector[f->slot];
  if (!media(m)->storage.write(media(m)->storage.user, id->offset, f->data,
                               f->data_pos)) {
    m->disk_writes++;
    id->st1 = 0x20;
    id->st2 = 0x20 | (((f->command[0] & 31) == 9) ? 0x40 : 0);
    if (m->disk_format[f->unit]) {
      uint8_t flags[] = {id->st1, id->st2};
      media(m)->storage.write(media(m)->storage.user,
                              tr->header + 0x1c + 8 * f->slot, flags, 2);
    }
  }
}
static void not_ready(robotron *m) {
  robotron_flush_interrupted_write(m);
  finish(m, 0);
  m->fdc.result[0] |= 0x48; /* Abnormal termination + NR. */
}
void robotron_drive_door(robotron *m, unsigned u, unsigned open) {
  if (u > 1 || m->drive[u].door_open == !!open) return;
  m->drive[u].door_open = !!open;
  m->drive[u].ready = m->drive[u].ready_indexes = 0;
  m->drive[u].loaded = 0;
  if (open && m->fdc.unit == u && m->fdc.phase == 2) not_ready(m);
}
static void begin_execution(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (!robotron_drive_ready(m, f->unit)) {
    not_ready(m);
    return;
  }
  robotron_drive *d = &m->drive[f->unit];
  if (!d->loaded) {
    unsigned delay = f->head_load_ticks;
    if (delay < ROBOTRON_HEAD_LOAD_TICKS)
      delay = ROBOTRON_HEAD_LOAD_TICKS;
    d->loaded = 1;
    d->load_at = m->cpu.cycles + delay;
  }
  d->unload_at = 0;
  f->phase = 2;
  f->search = 1;
  f->data_pos = 0;
  f->ready_at = UINT64_MAX;
  f->slot = 0;
}
static void sector(robotron *m) {
  robotron_fdc *f = &m->fdc;
  f->data_pos = 0;
  f->scan_compare = 0;
  f->read_id = 0;
  f->error2 = 0;
  if (!media(m) || f->n > 5 || !media(m)->storage.read) {
    finish(m, 4);
    return;
  }
  if (f->write == 1 && !media(m)->writable) {
    finish(m, 2);
    return;
  }
  f->data_len = f->n ? 128u << f->n : (f->command[8] ? f->command[8] : 128);
  if (f->data_len > (128u << f->n))
    f->data_len = 128u << f->n;
  begin_execution(m);
}
/* Exact 250 kbit/s byte cadence, rounded only at each event boundary. */
static uint64_t byte_at(const robotron_fdc *f, unsigned index) {
  return f->byte_origin + ((uint64_t)index * 79872 + 624) / 625;
}
static void transfer_done(robotron *m);
static void floppy_tick(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (f->phase != 2)
    return;
  if (!robotron_drive_ready(m, f->unit)) {
    not_ready(m);
    return;
  }
  robotron_drive *d = &m->drive[f->unit];
  if (f->search == 4) { /* Read Track starts at the next index. */
    if (m->cpu.cycles < f->ready_at)
      return;
    f->search = 1;
    f->track_count = 1;
  }
  if (f->search == 6) { /* Format clocks the data/filler between ID tuples. */
    if (m->cpu.cycles < f->ready_at)
      return;
    unsigned slot = f->data_pos / 4 - 1;
    const uint8_t *id = f->data + 4 * slot;
    if (id[3] != f->n ||
        robotron_format_sector(m, f->unit, f->physical[f->unit], f->head, id,
                               f->command[4], f->command[5], slot)) {
      finish(m, 4);
      return;
    }
    m->disk_writes++;
    f->sector = id[2];
    if (f->data_pos == f->data_len) {
      finish(m, 0);
      return;
    }
    f->search = 0;
    f->ready_at =
        byte_at(f, 162 + (slot + 1) * ((128u << f->n) + 62 + f->command[4]));
    return;
  }
  if (f->search == 5) { /* Finish clocking zero padding after host underrun. */
    if (m->cpu.cycles >= f->ready_at)
      transfer_done(m);
    return;
  }
  if (f->search == 1) {
    if ((f->seeking & (1u << f->unit)) || m->cpu.cycles < d->load_at ||
        m->cpu.cycles < d->settle_at)
      return;
    robotron_track *tr = track(m);
    unsigned phase = m->rotation[f->unit], wait = ROBOTRON_REVOLUTION_TICKS;
    int found = -1;
    f->search_index = d->index_count;
    if (f->read_track && !f->track_count) {
      f->ready_at = m->cpu.cycles + ROBOTRON_REVOLUTION_TICKS - phase;
      f->search = 4;
      return;
    }
    if (f->formatting) {
      f->ready_at = m->cpu.cycles + ROBOTRON_REVOLUTION_TICKS - phase;
      f->byte_origin = f->ready_at;
      f->ready_at = byte_at(f, 162);
      f->search = 0;
      return;
    }
    for (unsigned i = 0; tr && i < tr->count; i++) {
      robotron_sector *id = &tr->sector[i];
      if (id->st1 & 1)
        continue; /* No ID address mark to find. */
      if (!f->read_id && !f->read_track &&
          (id->c != f->command[2] || id->h != f->id_head ||
           id->r != f->sector || id->n != f->n))
        continue;
      unsigned delta = (id->id_phase + ROBOTRON_REVOLUTION_TICKS - phase) %
                       ROBOTRON_REVOLUTION_TICKS;
      if (delta < wait) {
        wait = delta;
        found = (int)i;
      }
    }
    if (found < 0) {
      f->search = 2;
      return;
    }
    f->slot = (unsigned)found;
    robotron_sector *id = &tr->sector[f->slot];
    f->result_c = id->c;
    if (f->read_track) {
      if (id->n != f->n) {
        finish(m, 4);
        return;
      }
      f->track_match |= id->c == f->command[2] && id->h == f->command[3] &&
                        id->r == f->command[4] && id->n == f->command[5];
      f->track_st1 |= id->st1;
      f->track_st2 |= id->st2 & ~0x40u;
    }
    if (!f->read_track && (id->st1 & 0x20) && !(id->st2 & 0x20)) {
      f->search = 3;
      f->ready_at = m->cpu.cycles + wait;
      return;
    }
    if (!f->read_id && f->write != 1 && ((id->st1 & 4) || (id->st2 & 1))) {
      f->search = 3;
      f->ready_at = m->cpu.cycles + wait;
      return;
    }
    if (!f->read_id && !f->read_track && f->write != 1 &&
        (f->command[0] & 32) &&
        (!!(id->st2 & 64) != ((f->command[0] & 31) == 12))) {
      if (f->sector < f->eot)
        f->sector++;
      else if ((f->command[0] & 128) && !f->head) {
        f->head = f->id_head = 1;
        f->sector = 1;
      } else {
        finish(m, 0x80);
        return;
      }
      f->search = 1;
      return;
    }
    if (f->read_id) {
      f->sector = id->r;
      f->n = id->n;
    }
    f->ready_at =
        m->cpu.cycles + wait + (f->read_id ? 0 : id->data_phase - id->id_phase);
    f->byte_origin = f->ready_at;
    f->search = 0;
    if (!f->read_id && f->write != 1) {
      if (media(m)->storage.read(media(m)->storage.user, id->offset, f->data,
                                 f->data_len)) {
        finish(m, 4);
        return;
      }
      m->disk_reads++;
    }
  }
  if (f->search == 3) {
    if (m->cpu.cycles >= f->ready_at) {
      robotron_sector *id = &track(m)->sector[f->slot];
      f->error2 = id->st2 & 1;
      finish(m, id->st1 ? id->st1 : 1);
    }
    return;
  }
  if (f->search == 2) {
    if ((unsigned)(d->index_count - f->search_index) >= 2) {
      robotron_track *tr = track(m);
      if (tr)
        for (unsigned i = 0; i < tr->count; i++)
          if (tr->sector[i].r == f->sector && tr->sector[i].c != f->command[2])
            f->error2 = tr->sector[i].c == 255 ? 0x12 : 0x10;
      finish(m, tr && tr->count ? 4 : 1);
    }
    return;
  }
  if (f->read_id && m->cpu.cycles >= f->ready_at) {
    robotron_sector *id = &track(m)->sector[f->slot];
    f->result_c = id->c;
    finish(m, (id->st2 & 0x20) ? 0 : (id->st1 & 0x20));
    f->result[4] = id->h;
  } else if (!f->read_id && m->cpu.cycles > f->ready_at + 103) {
    /* Keep the media clock running on write underrun, filling the tail with
     * zeros as the controller does, and still report OR to the host. */
    if (f->write == 1 && !f->formatting) {
      memset(f->data + f->data_pos, 0, f->data_len - f->data_pos);
      f->write_fault = 0x10;
      f->search = 5;
      f->ready_at = byte_at(f, f->data_len);
    } else
      finish(m, 0x10);
  }
}
static void transfer_done(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (f->write == 1) {
    robotron_track *tr = track(m);
    if (!tr || f->slot >= tr->count ||
        media(m)->storage.write(media(m)->storage.user,
                                tr->sector[f->slot].offset, f->data,
                                f->data_len)) {
      finish(m, 2);
      return;
    }
    if (m->disk_format[f->unit]) {
      uint8_t zero[2] = {0, (f->command[0] & 31) == 9 ? 0x40 : 0};
      if (media(m)->storage.write(media(m)->storage.user,
                                  tr->header + 0x1c + 8 * f->slot, zero, 2)) {
        finish(m, 2);
        return;
      }
      tr->sector[f->slot].st1 = 0;
      tr->sector[f->slot].st2 = zero[1];
    }
    m->disk_writes++;
    if (!m->disk_format[f->unit]) {
      tr->sector[f->slot].st1 = 0;
      tr->sector[f->slot].st2 = (f->command[0] & 31) == 9 ? 0x40 : 0;
    }
    if (f->write_fault) {
      finish(m, f->write_fault);
      return;
    }
  }
  if (f->read_track) {
    if (f->tc || f->track_count >= f->eot) {
      f->error2 = f->track_st2;
      finish(m, f->track_st1 | (f->track_match ? 0 : 4) | (f->tc ? 0 : 0x80));
    } else {
      f->track_count++;
      f->data_pos = 0;
      f->search = 1;
      f->ready_at = UINT64_MAX;
    }
    return;
  }
  if (f->write != 1) {
    robotron_sector *id = &track(m)->sector[f->slot];
    unsigned flags =
        (id->st2 & ~0x40u) |
        ((!!(id->st2 & 64) != ((f->command[0] & 31) == 12)) ? 64 : 0);
    if (id->st1 || flags) {
      f->error2 = flags;
      finish(m, id->st1);
      return;
    }
  }
  if (f->scan_mode &&
      (f->scan_mode == 17 ? f->scan_compare == 0
                          : (f->scan_mode == 25 ? f->scan_compare <= 0
                                                : f->scan_compare >= 0))) {
    finish(m, 0);
    return;
  }
  if (f->tc) {
    if (f->sector < f->eot)
      f->sector++;
    else {
      f->sector = 1;
      if ((f->command[0] & 128) && !f->head) {
        f->head = f->id_head = 1;
        finish(m, 0);
        return;
      }
      finish(m, 0);
      f->result[3]++; /* next CHRN is not a physical seek */
      return;
    }
    finish(m, 0);
  } else if (f->sector < f->eot) {
    f->sector++;
    sector(m);
  } else if ((f->command[0] & 128) && !f->head) {
    f->head = f->id_head = 1;
    f->sector = 1;
    sector(m);
  } else {
    finish(m, 0x80); /* EOT without terminal count. */
  }
}
static unsigned command_length(uint8_t c) {
  switch (c & 31) {
  case 3:
    return 3;
  case 4:
  case 7:
  case 10:
    return 2;
  case 15:
    return 3;
  case 13:
    return 6;
  case 2:
  case 9:
  case 12:
  case 5:
  case 6:
  case 17:
  case 25:
  case 29:
    return 9;
  default:
    return 1;
  }
}
static void command(robotron *m, uint8_t v) {
  robotron_fdc *f = &m->fdc;
  if (f->phase || f->reset)
    return;
  if (!f->cmd_pos)
    f->cmd_len = command_length(v);
  f->command[f->cmd_pos++] = v;
  if (f->cmd_pos < f->cmd_len)
    return;
  f->cmd_pos = 0;
  uint8_t *c = f->command;
  unsigned op = c[0] & 31;
  f->tc = 0;
  f->read_track = f->track_count = f->track_match = 0;
  f->track_st1 = f->track_st2 = f->write_fault = 0;
  f->scan_mode = 0;
  f->formatting = f->read_id = f->search = f->error2 = 0;
  if (op == 3) {
    f->step_ticks = ((16 - (c[1] >> 4)) * 39936 + 9) / 10;
    unsigned hlt = c[2] >> 1, hut = c[1] & 15;
    f->head_load_ticks = ((hlt ? hlt : 128) * 79872 + 9) / 10;
    f->head_unload_ticks = ((hut ? hut : 16) * 638976 + 9) / 10;
    return;
  }
  if (op == 8) {
    if (f->reset_queue) {
      unsigned u = 0;
      while (!(f->reset_queue & (1u << u)))
        u++;
      f->reset_queue &= ~(1u << u);
      f->result[0] = 0xc0 | u;
      f->result[1] = f->cylinder[u];
      result(m, 2);
      f->pending = !!(f->reset_queue | f->seek_done);
      return;
    }
    unsigned u = 0;
    while (u < 4 && !(f->seek_done & (1u << u)))
      u++;
    f->result[0] = u < 4 ? (uint8_t)(f->seek_status[u] | u) : 0x80;
    if (u < 4) {
      f->result[1] = (uint8_t)f->cylinder[u];
      f->seek_done &= ~(1u << u);
    }
    result(m, u < 4 ? 2 : 1);
    f->pending = !!f->seek_done;
    return;
  }
  f->unit = c[1] & 3;
  f->head = f->id_head = (c[1] >> 2) & 1;
  f->result_c = f->cylinder[f->unit];
  if (op == 4) {
    f->result[0] = (c[1] & 7) | 8 |
                   (robotron_drive_ready(m, f->unit) ? 32 : 0) |
                   (f->physical[f->unit] ? 0 : 16) |
                   (media(m) && media(m)->writable ? 0 : 64);
    result(m, 1);
  } else if (op == 7 || op == 15) {
    unsigned target = op == 7 ? 0 : c[2];
    f->seek_target[f->unit] = target;
    f->recalibrate[f->unit] = op == 7;
    f->pulses[f->unit] = 0;
    f->seek_status[f->unit] = 0x20;
    f->seek_interval[f->unit] = f->step_ticks ? f->step_ticks : 23962;
    f->seek_at[f->unit] = m->cpu.cycles + f->seek_interval[f->unit];
    f->seeking |= 1u << f->unit;
  } else if (op == 10) {
    f->read_id = 1;
    f->write = 0;
    f->data_len = 1;
    f->n = 3;
    if (!media(m) || !media(m)->storage.read) {
      finish(m, 4);
      return;
    }
    begin_execution(m);
  } else if (op == 13) {
    f->n = c[2];
    f->sector = 1;
    if (!media(m) || !media(m)->storage.read || c[2] > 5 || !c[3] ||
        c[3] > ROBOTRON_TRACK_SECTORS || !track(m) || c[3] != track(m)->count) {
      finish(m, 4);
      return;
    }
    if (!media(m)->writable) {
      finish(m, 2);
      return;
    }
    f->formatting = f->write = 1;
    f->data_pos = 0;
    f->data_len = c[3] * 4;
    begin_execution(m);
  } else if (op == 2 || op == 5 || op == 6 || op == 9 || op == 12 || op == 17 ||
             op == 25 || op == 29) {
    if (!media(m)) {
      f->sector = c[4];
      f->n = c[5];
      finish(m, 4);
      return;
    }
    f->id_head = c[3];
    f->sector = c[4];
    f->n = c[5];
    f->eot = c[6];
    f->scan_mode = op >= 17 ? op : 0;
    f->write = op >= 17 ? 2 : (op == 5 || op == 9);
    f->read_track = op == 2;
    if (op == 9 && !m->disk_format[f->unit]) {
      finish(m, 2); /* Raw export cannot preserve a deleted address mark. */
      return;
    }
    sector(m);
  } else {
    f->result[0] = 0x80;
    result(m, 1);
  }
}
static int ready(robotron *m) {
  return !m->fdc.reset && m->fdc.phase == 2 && !m->fdc.search &&
         !m->fdc.read_id && robotron_drive_ready(m, m->fdc.unit) &&
         m->cpu.cycles >= m->fdc.ready_at &&
         m->cpu.cycles <= m->fdc.ready_at + 103;
}
static uint8_t fdc_read(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (f->phase == 1) {
    uint8_t v = f->result[f->result_pos++];
    if (f->result_pos == f->result_len)
      f->phase = 0;
    return v;
  }
  if (ready(m) && !f->write) {
    uint8_t v = f->data[f->data_pos++];
    f->ready_at = byte_at(f, f->data_pos);
    if (f->data_pos == f->data_len)
      transfer_done(m);
    return v;
  }
  return 0xff;
}
static void fdc_write(robotron *m, uint8_t v) {
  if (ready(m) && m->fdc.write) {
    robotron_fdc *f = &m->fdc;
    if (f->scan_mode) {
      if (!f->scan_compare)
        f->scan_compare = (int)f->data[f->data_pos] - (int)v;
    } else
      f->data[f->data_pos] = v;
    f->data_pos++;
    if (f->formatting) {
      unsigned slot = (f->data_pos - 1) / 4, within = f->data_pos % 4;
      unsigned id = 162 + slot * ((128u << f->n) + 62 + f->command[4]);
      if (within)
        f->ready_at = byte_at(f, id + within);
      else {
        f->search = 6;
        f->ready_at = byte_at(f, id + 44 + (128u << f->n) + 2);
      }
      return;
    }
    f->ready_at = byte_at(f, f->data_pos);
    if (f->data_pos == f->data_len) {
      if (f->write == 1 && f->n == 0 && f->data_len < 128) {
        memset(f->data + f->data_len, 0, 128 - f->data_len);
        f->data_len = 128;
        f->search = 5;
        f->ready_at = byte_at(f, 128);
      } else
        transfer_done(m);
    }
  } else
    command(m, v);
}
static void dma_parameter(robotron_dma *d, uint8_t v) {
  unsigned tag = d->tags[d->tag_pos++];
  switch (tag) {
  case 1:
    d->a = (d->a & 0xff00) | v;
    break;
  case 2:
    d->a = (d->a & 255) | (v << 8);
    break;
  case 3:
    d->count = (d->count & 0xff00) | v;
    break;
  case 4:
    d->count = (d->count & 255) | (v << 8);
    break;
  case 5:
    d->b = (d->b & 0xff00) | v;
    break;
  case 6:
    d->b = (d->b & 255) | (v << 8);
    break;
  case 7:
    d->irq_control = v;
    if (v & 8)
      d->tags[d->tag_count++] = 9;
    if (v & 16)
      d->tags[d->tag_count++] = 8;
    break;
  case 8:
    d->vector = v;
    break;
  default:
    break;
  }
  if (d->tag_pos == d->tag_count)
    d->tag_pos = d->tag_count = 0;
}
static void dma_write(robotron *m, uint8_t v) {
  robotron_dma *d = &m->dma;
  if (d->tag_count) {
    dma_parameter(d, v);
    return;
  }
  if (d->mask_pending) {
    d->mask = v;
    d->mask_pending = 0;
    d->read_pos = 0;
    return;
  }
  if (v != 0xa7)
    d->mask = 0;
  switch (v) {
  case 0xc3:
    memset(d, 0, sizeof(*d));
    d->status = 0x38;
    d->vector = 0x14;
    return;
  case 0xbb:
    d->mask_pending = 1;
    return;
  case 0x8b:
    d->status |= 0x30;
    d->irq = 0;
    return;
  case 0xab:
    d->irq_enabled = 1;
    return;
  case 0xaf:
    d->irq_enabled = 0;
    return;
  case 0xbf:
    d->mask = 1;
    d->read_pos = 0;
    return;
  case 0xa7:
    d->read_pos = 0;
    return;
  case 0xa3:
    d->irq = d->irq_enabled = d->force_ready = d->in_service = 0;
    d->status |= 8;
    return;
  case 0xb3:
    d->force_ready = 1;
    return;
  case 0x83:
    d->enabled = 0;
    return;
  case 0x87:
    d->enabled = 1;
    return;
  case 0xcf:
    d->run_a = d->a;
    d->run_b = d->b;
    d->force_ready = 0; /* fall through */
  case 0xd3:
    d->remaining = (unsigned)d->count + 1;
    d->transferred = 0;
    d->status |= 0x30;
    return;
  default:
    break;
  }
  if ((v & 0x87) == 0) {
    d->b_mode = (v >> 4) & 3;
    d->b_io = (v >> 3) & 1;
    if (v & 0x40)
      d->tags[d->tag_count++] = 9;
  } else if ((v & 0x87) == 4) {
    d->a_mode = (v >> 4) & 3;
    d->a_io = (v >> 3) & 1;
    if (v & 0x40)
      d->tags[d->tag_count++] = 9;
  } else if (!(v & 128)) {
    d->direction = (v >> 2) & 1;
    for (unsigned i = 0; i < 4; i++)
      if (v & (8 << i))
        d->tags[d->tag_count++] = i + 1;
  } else if ((v & 0xc7) == 0x82) {
    d->ready_high = (v >> 3) & 1;
  } else if ((v & 0x83) == 0x81) {
    for (unsigned i = 0; i < 3; i++)
      if (v & (4 << i))
        d->tags[d->tag_count++] = 5 + i;
  } else if ((v & 0x83) == 0x80) {
    d->irq_enabled = (v >> 5) & 1;
    if (v & 64)
      d->enabled = 1;
    for (unsigned i = 3; i <= 4; i++)
      if (v & (1 << i))
        d->tags[d->tag_count++] = 9;
  }
}
static int dma_ready(robotron *m) {
  /* PC-1715W inverts FDC DRQ before the Z80 DMA RDY input. */
  return m->dma.force_ready || ((!ready(m)) == m->dma.ready_high);
}
static uint8_t dma_read(robotron *m) {
  robotron_dma *d = &m->dma;
  uint8_t s = (d->status & 0xfd) | (dma_ready(m) ? 0 : 2);
  if (!d->mask)
    return s;
  uint8_t values[] = {s,
                      d->transferred & 255,
                      d->transferred >> 8,
                      d->run_a & 255,
                      d->run_a >> 8,
                      d->run_b & 255,
                      d->run_b >> 8};
  for (unsigned i = 0; i < 7; i++) {
    unsigned pos = d->read_pos;
    d->read_pos = (pos + 1) % 7;
    if (d->mask & (1 << pos))
      return values[pos];
  }
  return s;
}
static void ctc_write(robotron *m, unsigned n, uint8_t v) {
  robotron_timer *t = &m->ctc[n];
  if (t->waiting) {
    t->constant = v;
    t->counter = v ? v : 256;
    t->waiting = 0;
    t->prescaler = 0;
    t->control &= ~2;
    return;
  }
  if (!(v & 1)) {
    m->ctc_vector[n / 4] = v & 0xf8;
    return;
  }
  t->control = v;
  t->waiting = (v >> 2) & 1;
  if (v & 2)
    t->pending = t->in_service = 0;
}
static uint8_t input_value(void *p, uint16_t a) {
  robotron *m = p;
  a &= 255;
  if (a == 0)
    return dma_read(m);
  if (a >= 4 && a <= 11)
    return (uint8_t)m->ctc[a - 4].counter;
  if (a == 0x1c || a == 0x40)
    return m->fdc.seeking |
           (m->fdc.reset ? 0 : (m->fdc.phase == 2 && !ready(m) ? 0 : 0x80)) |
           (m->fdc.phase || m->fdc.cmd_pos ? 16 : 0) |
           ((m->fdc.phase == 1 || (ready(m) && !m->fdc.write)) ? 64 : 0);
  if (a == 0x1d || a == 0x41)
    return fdc_read(m);
  if (a >= 0x34 && a <= 0x37)
    return 1;
  if (m->keyboard_enabled && (a == 0x0c || a == 0x0e))
    return robotron_sio_read(m, a == 0x0e);
  if (a == 0x0e) {
    unsigned reg = m->sio_pointer[0];
    m->sio_pointer[0] = 0;
    return reg == 1
               ? (!m->tx_full && !m->tx_clocks)
               : (0x78 | (!m->tx_full << 2) | (m->key_read != m->key_write) |
                  ((m->tx_pending && (m->sio_regs[0][1] & 2)) << 1));
  }
  if (a == 0x0c) {
    if (m->key_read == m->key_write)
      return 0;
    return m->keys[m->key_read++ & 255];
  }
  if (a == 0x19) {
    /* Intel 8275 status: reading clears IR/LP/IC/DU/FO, not IE or VE. */
    uint8_t status = m->crtc_status;
    m->crtc_status &= 0x44;
    return status;
  }
  if (a == 0x0f || a == 0x14 || a == 0x15)
    return 0x64;
  if (a == 0x0d || a == 0x16 || a == 0x17 || a == 0x18 || a == 0x19)
    return 0;
  return 0xff;
}
uint8_t robotron_input(void *p, uint16_t a) {
  robotron *m = p;
  uint8_t v = input_value(p, a);
  dac_trace_emit(&m->trace, "IR", a, v, m->cpu.cycles, 2);
  return v;
}
static void video_restart(robotron *m);
void robotron_output(void *p, uint16_t a, uint8_t v) {
  robotron *m = p;
  dac_trace_emit(&m->trace, "IW", a, v, m->cpu.cycles, 2);
  a &= 255;
  if (a == 0)
    dma_write(m, v);
  else if (a == 0x0c) {
    if (!m->tx_full && (m->sio_regs[0][5] & 8)) {
      m->tx_holding = v;
      m->tx_full = 1;
      m->tx_pending = 0;
    }
  } else if (a == 0x0e || a == 0x0f) {
    robotron_sio_control(m, a & 1, v);
  } else if (a >= 4 && a <= 11)
    ctc_write(m, a - 4, v);
  else if (a == 0x1d || a == 0x41)
    fdc_write(m, v);
  else if (a >= 0x24 && a <= 0x27)
    m->bank = v;
  else if (a >= 0x20 && a <= 0x23) {
    if ((m->krfd ^ v) & 64) {
      unsigned cylinders[4], physical[4];
      memcpy(cylinders, m->fdc.cylinder, sizeof(cylinders));
      memcpy(physical, m->fdc.physical, sizeof(physical));
      robotron_flush_interrupted_write(m);
      memset(&m->fdc, 0, sizeof(m->fdc));
      memcpy(m->fdc.cylinder, cylinders, sizeof(cylinders));
      memcpy(m->fdc.physical, physical, sizeof(physical));
      m->fdc.reset = !(v & 64);
      if (!m->fdc.reset) {
        m->fdc.reset_queue = 15;
        m->fdc.pending = 1;
      }
    }
    m->krfd = v;
  } else if (a >= 0x28 && a <= 0x2b)
    m->motor = v;
  else if (a == 0x19) {
    unsigned incomplete = m->crtc_pos < m->crtc_end;
    if (m->raster.stopped == 2) m->raster.stopped = 0;
    m->crtc_pos = m->crtc_end = 0;
    switch (v >> 5) {
    case 0:
      m->display_on = m->crtc_status = 0;
      memset(&m->raster, 0, sizeof(m->raster));
      m->raster.blank_from = 24;
      m->crtc_end = 4;
      break;
    case 1:
      m->raster.dma = v & 31;
      m->raster.stopped = 0;
      m->display_on = 1;
      m->crtc_status |= 0x44;
      video_restart(m);
      break;
    case 2:
      m->display_on = 0;
      m->crtc_status &= ~4;
      m->raster.remaining = 0;
      break;
    case 4:
      m->crtc_pos = 4;
      m->crtc_end = 6;
      break;
    case 5:
      m->crtc_status |= 0x40;
      break;
    case 6:
      m->crtc_status &= ~0x40;
      break;
    case 7: /* Preset holds counters until another command. */
      m->raster.character = m->raster.row = m->raster.fraction = 0;
      m->raster.stopped = 2;
      break;
    default:
      break;
    }
    if (incomplete)
      m->crtc_status |= 8; /* interrupted parameter string */
  } else if (a == 0x18 && m->crtc_pos < m->crtc_end) {
    unsigned pos = m->crtc_pos++;
    if (pos < 4)
      m->crtc[pos] = v;
    else
      m->cursor[pos - 4] = v;
  } else if (a == 0x18)
    m->crtc_status |= 8; /* excess parameter */
}
/* Daisy chain: DMA, CTC2 channels 0..3, SIO A RX then TX. CTC0 has no INT. */
static int interrupt_source(robotron *m) {
  if (m->dma.in_service)
    return -1;
  if (m->dma.irq)
    return 0;
  for (unsigned i = 0; i < 4; i++) {
    if (m->ctc[i].in_service)
      return -1;
    if (m->ctc[i].pending)
      return (int)i + 1;
  }
  if (m->rx.in_service)
    return -1;
  if (m->rx.pending)
    return 5;
  if (m->tx_in_service)
    return -1;
  if (m->tx_pending && (m->sio_regs[0][1] & 2))
    return 6;
  return -1;
}
static uint8_t ack(void *p) {
  robotron *m = p;
  int source = interrupt_source(m);
  if (source == 0) {
    m->dma.irq = 0;
    m->dma.in_service = 1;
    return m->dma.irq_vector;
  }
  if (source == 6) {
    m->tx_in_service = 1;
    return (m->sio_regs[1][1] & 4) ? (m->sio_regs[1][2] & 0xf1) | 8
                                   : m->sio_regs[1][2];
  }
  if (source == 5) {
    m->rx.pending = 0;
    m->rx.in_service = 1;
    return (m->sio_regs[1][1] & 4) ? (m->sio_regs[1][2] & 0xf1) | 12
                                   : m->sio_regs[1][2];
  }
  if (source > 0) {
    m->ctc[source - 1].pending = 0;
    m->ctc[source - 1].in_service = 1;
    return m->ctc_vector[0] + 2 * (source - 1);
  }
  return 0xff;
}
static void reti(robotron *m) {
  if (m->dma.in_service) {
    m->dma.in_service = 0;
    return;
  }
  for (unsigned i = 0; i < 4; i++)
    if (m->ctc[i].in_service) {
      m->ctc[i].in_service = 0;
      return;
    }
  if (m->rx.in_service)
    m->rx.in_service = 0;
  else
    m->tx_in_service = 0;
}

void robotron_init(robotron *m) {
  memset(m, 0, sizeof(*m));
  memset(m->prom, 15, 256);
  m->dma.vector = 0x14;
  m->krfd = 0x40;
  m->raster.blank_from = 24;
  m->crtc[0] = 79;
  m->crtc[1] = 23;
  m->crtc[2] = 0x6f;
  m->crtc[3] = 0x60;
  m->cursor[0] = m->cursor[1] = 255;
  dac_z80_init(&m->cpu, (dac_z80_bus){m, robotron_read, robotron_write,
                                      robotron_input, robotron_output, ack});
}
int robotron_load(robotron *m, const void *r, size_t nr, const void *p,
                  size_t np) {
  if (!m || !r || !p || nr != 2048 || np != 256)
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  memcpy(m->rom, r, nr);
  memcpy(m->prom, p, np);
  return 0;
}
int robotron_key(robotron *m, uint8_t key) {
  if (m->key_write - m->key_read > 254)
    return -ENOSPC;
  m->keys[m->key_write++ & 255] = 0xe0;
  m->keys[m->key_write++ & 255] =
      (key == 13 || key == 10) ? 0x9e : (key == 27 ? 0x9b : key);
  return 0;
}
static void advance(uint16_t *a, unsigned mode) {
  if (mode == 0)
    (*a)--;
  else if (mode == 1)
    (*a)++;
}
int robotron_keyboard_load(robotron *m, const void *rom, size_t n) {
  if (!rom || n != 2048 || m->cpu.cycles)
    return -EINVAL;
  robotron_keyboard_init(&m->keyboard, rom, m, robotron_serial_clock);
  m->keyboard_enabled = 1;
  m->rx.first = 1;
  return 0;
}
/* Intel 8275 row buffer and 16 x 7-bit invisible-attribute FIFO.
 * Fill the complete row before reading it out: a 17th FIFO byte overwrites
 * entry zero (including the character displayed by the first attribute).
 * This is bounded stream decoding, not the board's cycle-level DMA circuit. */
static unsigned video_columns(const robotron *m) {
  unsigned n = (m->crtc[0] & 127) + 1;
  return n > 80 ? 80 : n;
}
static unsigned video_rows(const robotron *m) {
  unsigned n = (m->crtc[1] & 63) + 1;
  return n > 24 ? 24 : n;
}
static unsigned video_row_clocks(const robotron *m) {
  return (video_columns(m) + 2 * ((m->crtc[3] & 15) + 1)) *
         ((m->crtc[2] & 15) + 1) * ((m->crtc[0] & 128) ? 2 : 1);
}
static unsigned video_total_rows(const robotron *m) {
  return video_rows(m) + (m->crtc[1] >> 6) + 1;
}
static void video_fetch_row(const robotron *m, unsigned *position,
                            robotron_video_row *row, unsigned ignored) {
  unsigned written = 0, burst = 1u << (m->raster.dma & 3);
  memset(row, 0, sizeof(*row));
  memset(row->code, 0xf0, sizeof(row->code));
  for (unsigned col = 0; col < video_columns(m); col++) {
    uint8_t code = m->vram[(*position)++ % 1920];
    row->bytes++;
    row->code[col] = code;
    if (!ignored && !(m->crtc[3] & 64) && (code & 0xc0) == 0x80) {
      row->fifo[written++ & 15] = m->vram[(*position)++ % 1920] & 127;
      row->bytes++;
      if (written > 16) row->overflow = 1;
    } else if ((!ignored && code == 0xf1) || (ignored < 2 && code == 0xf3)) {
      // Intel: one extra dummy read unless last byte of burst or row.
      if (col + 1 < video_columns(m) && row->bytes % burst) {
        (*position)++; row->bytes++;
      }
      row->stop_screen = code == 0xf3;
      break;
    }
    if (!ignored && code == 0xf0) ignored = 1;
    if (code == 0xf2) { ignored = 2; row->ignore_screen = 1; }
  }
}
static void video_schedule_row(robotron *m, unsigned row) {
  robotron_raster *r = &m->raster;
  if (!m->display_on || r->stopped || r->underrun) return;
  if (row == 0) r->stream = r->ignored = 0;
  robotron_video_row buffer;
  video_fetch_row(m, &r->stream, &buffer, r->ignored ? 2 : 0);
  r->pending_row = buffer;
  r->pending_valid = 1;
  if (buffer.ignore_screen) r->ignored = 1;
  r->stream %= 1920;
  unsigned burst = 1u << (r->dma & 3), spacing = (r->dma >> 2) * 8;
  if (spacing) spacing--;
  // Idealized local DACK: one byte per character clock, programmed burst gaps.
  r->remaining = buffer.bytes + ((buffer.bytes - 1) / burst) * spacing;
  r->overflow = buffer.overflow;
  if (buffer.stop_screen) r->stopped = 1;
}
static void video_restart(robotron *m) {
  robotron_raster *r = &m->raster;
  r->fraction = r->character = r->underrun = r->stopped = 0;
  r->row = video_total_rows(m) - 1;
  r->blank_from = 24;
  r->pending_valid = r->valid_rows = r->field = r->end_screen = 0;
  memset(r->scanout, 0, sizeof(r->scanout));
  video_schedule_row(m, 0);
}
/* Latch only completed fetches at the scanout row boundary. Carry field
 * attributes here, not across a mixture of rows in the host renderer. */
static void video_latch_row(robotron *m) {
  robotron_raster *r = &m->raster;
  robotron_video_row *out = &r->scanout[r->row];
  if (r->row == 0) r->field = r->end_screen = 0;
  memset(out, 0, sizeof(*out));
  memset(out->code, 0xf0, sizeof(out->code));
  if (r->pending_valid && !r->underrun) *out = r->pending_row;
  out->field = r->field; out->end_screen = r->end_screen;
  r->pending_valid = 0;
  r->valid_rows |= 1u << r->row;
  for (unsigned col = 0; col < video_columns(m); col++) {
    uint8_t code = out->code[col];
    if (r->end_screen) break;
    if ((code & 0xc0) == 0x80) r->field = code & 63;
    if (code == 0xf2 || code == 0xf3) r->end_screen = 1;
    if (code >= 0xf0 && code <= 0xf3) break;
  }
}
static void video_clock(robotron *m) {
  robotron_raster *r = &m->raster;
  if (r->stopped == 2) return;
  // Rational accumulator avoids rounding drift and depends only on CPU ticks.
  r->fraction += 45; /* 1.728 MHz / 3.9936 MHz = 45 / 104 */
  if (r->fraction < 104) return;
  r->fraction -= 104;
  if (r->remaining && !--r->remaining && r->overflow && m->display_on)
    m->crtc_status |= 1;
  if (++r->character < video_row_clocks(m)) return;
  r->character = 0;
  r->row = (r->row + 1) % video_total_rows(m);
  if (r->row == 0) { r->frames++; r->blank_from = 24; }
  if (r->row < video_rows(m)) {
    if (m->display_on && r->remaining) {
      m->crtc_status |= 2;
      r->underrun = 1; r->blank_from = r->row;
      r->remaining = 0;
    }
    video_latch_row(m);
    if (r->row == video_rows(m) - 1 && (m->crtc_status & 64))
      m->crtc_status |= 32; // IR flag only: CPU interrupt wiring unverified.
    if (r->row + 1 < video_rows(m)) video_schedule_row(m, r->row + 1);
  } else if (r->row == video_total_rows(m) - 1) {
    r->underrun = r->stopped = r->remaining = r->pending_valid = 0;
    video_schedule_row(m, 0); // Prefill during final vertical-retrace row.
  }
}

void robotron_run(robotron *m, unsigned ticks) {
  while (ticks--) {
    if (m->keyboard_enabled)
      robotron_keyboard_tick(&m->keyboard);
    for (unsigned u = 0; u < 4; u++)
      if ((m->fdc.seeking & (1u << u)) && m->cpu.cycles >= m->fdc.seek_at[u]) {
        robotron_fdc *f = &m->fdc;
        int recal = f->recalibrate[u];
        int step =
            recal ? f->physical[u] != 0 : f->cylinder[u] != f->seek_target[u];
        if (step) {
          int inward = !recal && f->cylinder[u] < f->seek_target[u];
          if (u < 2) {
            robotron_drive *d = &m->drive[u];
            d->from_q16 = robotron_head_position(m, u);
            d->step_at = m->cpu.cycles;
            d->settle_at =
                m->cpu.cycles + ROBOTRON_STEP_TICKS + ROBOTRON_SETTLE_TICKS;
            d->events[f->steps[u] % ROBOTRON_STEP_EVENTS] = m->cpu.cycles;
          }
          if (inward && f->physical[u] < 79)
            f->physical[u]++;
          if (!inward && f->physical[u])
            f->physical[u]--;
          if (!recal) {
            if (inward)
              f->cylinder[u]++;
            else
              f->cylinder[u]--;
          }
          f->steps[u]++;
          f->pulses[u]++;
        }
        if ((recal && (!f->physical[u] || f->pulses[u] >= 77)) ||
            (!recal && f->cylinder[u] == f->seek_target[u])) {
          if (recal) {
            f->cylinder[u] = 0;
            if (f->physical[u])
              f->seek_status[u] = 0x70;
          }
          f->seeking &= ~(1u << u);
          f->seek_done |= 1u << u;
          f->pending = 1;
        } else
          f->seek_at[u] += f->seek_interval[u];
      }
    floppy_tick(m);
    unsigned cascade = 0;
    for (unsigned i = 0; i < 8; i++) {
      robotron_timer *t = &m->ctc[i];
      if (!(t->control & 2) && !t->waiting && t->counter) {
        unsigned clock = 0;
        if (t->control & 0x40)
          clock = (i == 2 && cascade);
        else if (++t->prescaler >= ((t->control & 0x20) ? 256u : 16u)) {
          t->prescaler = 0;
          clock = 1;
        }
        if (clock && !--t->counter) {
          t->counter = t->constant ? t->constant : 256;
          t->pending = (t->control >> 7) & 1;
          if (i == 1)
            cascade = 1;
          if (i == 4)
            robotron_printer_clock(m);
        }
      }
    }
    robotron_dma *d = &m->dma;
    if (d->enabled && d->remaining && dma_ready(m)) {
      uint16_t src = d->direction ? d->run_a : d->run_b,
               dst = d->direction ? d->run_b : d->run_a;
      unsigned si = d->direction ? d->a_io : d->b_io,
               di = d->direction ? d->b_io : d->a_io;
      /* Board TC is DMA INT gated by KRFD. Set before the last byte. */
      int terminal = d->remaining == 1 && d->irq_enabled &&
                     (d->irq_control & 2) && !d->in_service && (m->krfd & 128);
      if (terminal && m->fdc.phase == 2)
        m->fdc.tc = 1;
      uint8_t v = si ? robotron_input(m, src) : robotron_read(m, src);
      if (di)
        robotron_output(m, dst, v);
      else
        robotron_write(m, dst, v);
      advance(&d->run_a, d->a_mode);
      advance(&d->run_b, d->b_mode);
      d->transferred++;
      if (!--d->remaining) {
        if (terminal && m->fdc.phase == 2) {
          /* Short writes finish the physical sector with zero padding. */
          if (m->fdc.formatting) {
            if (m->fdc.data_pos != m->fdc.data_len)
              finish(m, 4); /* Earlier completed sectors remain formatted. */
          } else if (m->fdc.write == 1) {
            memset(m->fdc.data + m->fdc.data_pos, 0,
                   m->fdc.data_len - m->fdc.data_pos);
            m->fdc.search = 5;
            m->fdc.ready_at = byte_at(&m->fdc, m->fdc.data_len);
          } else
            transfer_done(m);
        }
        d->enabled = 0;
        d->status = 0x19;
        if (d->irq_enabled && (d->irq_control & 2) && !d->in_service) {
          d->irq = 1;
          d->irq_vector =
              (d->irq_control & 32) ? (d->vector & 0xf9) | 4 : d->vector;
          d->status &= ~8;
        }
      }
      /* CPU bus ownership is paused while DMA transfers. */
      m->cpu.cycles++;
    } else {
      dac_z80_tick(&m->cpu, interrupt_source(m) >= 0, 0);
      if (m->cpu.pins & Z80_RETI)
        reti(m);
    }
    mechanics_tick(m);
    video_clock(m);
  }
}

/* Pure host drawing from latched controller rows. VRAM is sampled by the
 * scheduler only. Row-level sampling is not per-byte bus contention. */
void robotron_video(robotron *m, uint32_t *pixels, unsigned *width,
                    unsigned *height) {
  unsigned cols = video_columns(m), rows = video_rows(m);
  unsigned lines = (m->crtc[2] & 15) + 1, underline = m->crtc[2] >> 4;
  *width = cols * 8;
  *height = rows * lines;
  unsigned frame = m->raster.frames;
  for (unsigned row = 0; row < rows; row++) {
    const robotron_video_row buffer = m->raster.scanout[row];
    unsigned field = buffer.field, end_screen = buffer.end_screen;
    unsigned end_row = 0, fifo_read = 0;
    for (unsigned col = 0; col < cols; col++) {
      uint8_t ch = buffer.code[col];
      unsigned attr = field, blank = end_row || end_screen || !m->display_on ||
                                    !(m->raster.valid_rows & (1u << row));
      if ((ch & 0xc0) == 0x80) {
        if (!end_row && !end_screen)
          field = ch & 63;
        if (m->crtc[3] & 64)
          blank = 1;
        else {
          /* The invisible-attribute FIFO is seven bits wide: its next
           * byte is always glyph data, even when bit 7 was set. Intel
           * 8275 datasheet p.8-237, not another FA/CA/control command. */
          ch = buffer.fifo[fifo_read++ & 15];
          attr = field;
        }
      }
      if (ch >= 0xf0) {
        blank = 1;
        if (ch == 0xf0 || ch == 0xf1)
          end_row = 1;
        if (ch == 0xf2 || ch == 0xf3)
          end_screen = ch == 0xf3 ? 2 : 1;
      }
      unsigned character_attr = ch >= 0xc0 && ch < 0xf0;
      if (character_attr)
        /* CA inherits field reverse and GPA; highlight/blink are its own. */
        attr = (field & 0x1c) | (ch & 3);
      for (unsigned y = 0; y < lines; y++) {
        unsigned gy = (m->crtc[3] & 128) ? (y + lines - 1) % lines : y;
        uint8_t bits =
            m->chargen[((attr & 4) ? 2048 : 0) + gy * 128 + (ch & 127)];
        if (character_attr) {
          /* Intel 8275 CA truth table, cross-checked against MAME i8275
           * (Curt Coder/AJR, BSD-3-Clause; see NOTICE). Robotron does not
           * wire LA0/LA1 to the glyph decoder; retain its glyph bits. */
          static const uint8_t ca[3][16] = {
              {2, 2, 4, 4, 2, 4, 4, 4, 2, 4, 4, 0, 2, 0, 0, 0},
              {8, 12, 8, 12, 1, 12, 8, 1, 1, 4, 1, 0, 2, 0, 0, 0},
              {4, 4, 2, 2, 4, 4, 4, 2, 2, 4, 4, 0, 2, 0, 0, 0}};
          unsigned flags = ca[y < underline    ? 0
                              : y == underline ? 1
                                               : 2][(ch >> 2) & 15];
          if (flags & 2)
            bits = (flags & 1) ? 255 : 0;
        }
        if ((attr & 2) && (frame % 64 < 32))
          bits = 0;
        if ((attr & 32) && y == underline)
          bits = 255;
        if (attr & 16)
          bits ^= 255;
        unsigned format = (m->crtc[3] >> 4) & 3;
        if (row == m->cursor[1] && col == m->cursor[0] &&
            ((format & 2) || frame % 32 < 16)) {
          if (format & 1) {
            if (y == underline)
              bits = 255;
          } else
            bits ^= 255;
        }
        if (blank)
          bits = 0;
        for (unsigned x = 0; x < 8; x++)
          pixels[(row * lines + y) * *width + col * 8 + x] =
              (bits & (128 >> x)) ? ((attr & 1) ? 0xffb0ffcb : 0xff83e7a0)
                                  : 0xff101812;
      }
    }
  }
}

void robotron_rebind(robotron *m) {
  m->cpu.bus = (dac_z80_bus){
      m, robotron_read, robotron_write, robotron_input, robotron_output, ack};
  robotron_keyboard_rebind(&m->keyboard, m, robotron_serial_clock);
  memset(&m->trace, 0, sizeof(m->trace));
}
