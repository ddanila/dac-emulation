/* Physical ownership and text-generated combinations share hardware contacts.
 * The host queue is bounded transport, not an emulated PC 8042. */
static int key_bit(const uint8_t *bits, unsigned id) {
  return (bits[id / 8] >> (id % 8)) & 1;
}
static void key_set(uint8_t *bits, unsigned id, int down) {
  if (down)
    bits[id / 8] |= (uint8_t)(1u << (id % 8));
  else
    bits[id / 8] &= (uint8_t)~(1u << (id % 8));
}
static int key_valid(unsigned layout, unsigned id) {
  if (layout != 2)
    return id < 128 ? id % 8 < 6 : id == 128 || id == 129;
  if (id == 512)
    return 1; /* Pause's six-byte make sequence has no break. */
  if (id > 256 && id < 384) {
    switch (id - 256) {
    case 28:
    case 29:
    case 53:
    case 55:
    case 56:
    case 71:
    case 72:
    case 73:
    case 75:
    case 77:
    case 79:
    case 80:
    case 81:
    case 82:
    case 83:
      return 1;
    default:
      return 0;
    }
  }
  return id >= 1 && id <= 88;
}
static int key_modifier(unsigned id) {
  return id == 29 || id == 42 || id == 54 || id == 56 || id == 285 || id == 312;
}
static int key_repeatable(unsigned id) {
  return !key_modifier(id) && id != 58 && id != 69 && id != 70 && id != 311 &&
         id != 512;
}
int juku_keyboard_text_contacts(unsigned profile, unsigned key,
                                unsigned ids[3]) {
  if (profile >= JUKU_PROFILE_COUNT || key > 255 || !key || !ids)
    return -EINVAL;
  unsigned layout = profiles[profile].keyboard, shift = 0, ctrl = 0;
  int col = -1, row = -1;
  if (layout == 2) {
    unsigned scan = juku_at_scan((uint8_t)key, &shift, &ctrl);
    if (!scan)
      return -ENOTSUP;
    unsigned n = 0;
    if (shift)
      ids[n++] = 42;
    if (ctrl)
      ids[n++] = 29;
    ids[n++] = scan;
    return (int)n;
  }
  if (layout == 1) {
    int sh = 0, ct = 0;
    juku_juss_contact((uint8_t)key, &col, &row, &sh, &ct);
    shift = sh;
    ctrl = ct;
  } else {
    unsigned lc = key;
    if (key == 0x85 || key == 0x8e) {
      col = key == 0x85 ? 10 : 9;
      row = 2;
      ctrl = 1;
    }
    for (unsigned i = 0; i < sizeof KMAP / sizeof *KMAP; i++)
      if ((uint8_t)KMAP[i].c == lc) {
        col = KMAP[i].col;
        row = KMAP[i].bit;
        shift = KMAP[i].shift;
        break;
      }
    if (col < 0 && key >= 1 && key <= 26) {
      lc = 'a' + key - 1;
      ctrl = 1;
    } else if (key >= 'A' && key <= 'Z') {
      lc = key + 32;
      shift = 1;
    }
    if (col < 0)
      for (unsigned i = 0; i < sizeof KMAP / sizeof *KMAP; i++)
        if ((uint8_t)KMAP[i].c == lc) {
          col = KMAP[i].col;
          row = KMAP[i].bit;
          shift |= KMAP[i].shift;
          break;
        }
  }
  if (col < 0)
    return -ENOTSUP;
  unsigned n = 0;
  if (shift)
    ids[n++] = 128;
  if (ctrl)
    ids[n++] = 129;
  ids[n++] = (unsigned)(col * 8 + row);
  return (int)n;
}
static void key_effective(unsigned profile, const uint8_t *physical,
                          const uint8_t *text, uint8_t *effective) {
  memcpy(effective, physical, 65);
  for (unsigned k = 1; k < 256; k++)
    if (key_bit(text, k)) {
      unsigned ids[3];
      int n = juku_keyboard_text_contacts(profile, k, ids);
      for (int i = 0; i < n; i++)
        key_set(effective, ids[i], 1);
    }
}
static unsigned key_sequence(unsigned id, int down, uint8_t *out) {
  if (id == 512) {
    if (!down)
      return 0;
    const uint8_t pause[] = {0xe1, 0x1d, 0x45, 0xe1, 0x9d, 0xc5};
    memcpy(out, pause, sizeof pause);
    return sizeof pause;
  }
  if (id == 311) {
    const uint8_t make[] = {0xe0, 0x2a, 0xe0, 0x37},
                  brk[] = {0xe0, 0xb7, 0xe0, 0xaa};
    memcpy(out, down ? make : brk, 4);
    return 4;
  }
  unsigned n = 0;
  if (id >= 256)
    out[n++] = 0xe0;
  out[n++] = (uint8_t)((id & 127) | (down ? 0 : 128));
  return n;
}
static int key_commit(juku *j, const uint8_t *physical, const uint8_t *text,
                      unsigned owner) {
  uint8_t next[65], sequence[512];
  unsigned count = 0;
  key_effective(j->profile, physical, text, next);
  if (profiles[j->profile].keyboard == 2) {
    /* Break ordinary keys before modifiers; make modifiers before keys. */
    for (unsigned pass = 0; pass < 4; pass++)
      for (unsigned id = 1; id <= 512; id++) {
        int was = key_bit(j->key_effective, id), now = key_bit(next, id);
        if (was == now)
          continue;
        unsigned stage =
            now ? (key_modifier(id) ? 2 : 3) : (key_modifier(id) ? 1 : 0);
        if (stage == pass)
          count += key_sequence(id, now, sequence + count);
      }
    if (count > sizeof(j->at_queue) - j->at_count)
      return -EAGAIN;
    for (unsigned i = 0; i < count; i++)
      juku_at_enqueue(j, sequence[i]);
    if (j->key_repeat && !key_bit(next, j->key_repeat - 1))
      j->key_repeat = 0;
    if (owner && key_repeatable(owner - 1) && key_bit(next, owner - 1) &&
        !key_bit(j->key_effective, owner - 1)) {
      j->key_repeat = (uint16_t)owner;
      j->key_repeat_due = j->cpu.cyc + 1000000;
      j->key_repeat_fraction = 0;
    }
  }
  memcpy(j->key_physical, physical, 65);
  memcpy(j->key_text, text, 32);
  memcpy(j->key_effective, next, 65);
  j->live_keyboard = j->kbd_enabled = 1;
  j->kbd_start_vram = 0;
  return 0;
}
int juku_keyboard_contact(juku *j, unsigned id, int down) {
  if (!j || !key_valid(profiles[j->profile].keyboard, id) ||
      (down != 0 && down != 1))
    return -EINVAL;
  if (key_bit(j->key_physical, id) == down)
    return 0;
  uint8_t next[65];
  memcpy(next, j->key_physical, 65);
  key_set(next, id, down);
  return key_commit(j, next, j->key_text, down ? id + 1 : 0);
}
int juku_keyboard_release_all(juku *j) {
  if (!j)
    return -EINVAL;
  const uint8_t empty[65] = {0};
  int r = key_commit(j, empty, empty, 0);
  if (!r)
    j->live_key = 0;
  return r;
}
int juku_key(juku *j, uint8_t key, int down) {
  if (!j || (down != 0 && down != 1))
    return -EINVAL;
  uint8_t next[32];
  memcpy(next, j->key_text, 32);
  unsigned owner = 0;
  if (!key && !down)
    memset(next, 0, 32);
  else {
    unsigned ids[3];
    int n = juku_keyboard_text_contacts(j->profile, key, ids);
    if (n < 0)
      return n;
    if (key_bit(next, key) == down)
      return 0;
    key_set(next, key, down);
    if (down)
      owner = ids[n - 1] + 1;
  }
  int r = key_commit(j, j->key_physical, next, owner);
  if (!r) {
    if (down)
      j->live_key = key;
    else if (!key || key == j->live_key)
      j->live_key = 0;
  }
  return r;
}
static void juku_keyboard_tick(juku *j) {
  if (profiles[j->profile].keyboard != 2 || !j->key_repeat)
    return;
  if (j->cpu.cyc - j->key_repeat_due > ULONG_MAX / 2)
    return;
  uint8_t bytes[6];
  unsigned n = key_sequence(j->key_repeat - 1, 1, bytes);
  /* Reserve space for releases. No accumulated repeat burst under pressure. */
  if (j->at_count + n <= sizeof(j->at_queue) - 16)
    for (unsigned i = 0; i < n; i++)
      juku_at_enqueue(j, bytes[i]);
  unsigned period = 183333;
  if (++j->key_repeat_fraction == 3) {
    period++;
    j->key_repeat_fraction = 0;
  }
  j->key_repeat_due = j->cpu.cyc + period;
}
int juku_keyboard_state_valid(const juku *j) {
  if (j->kbd_col > 15) return 0;
  unsigned layout = profiles[j->profile].keyboard;
  for (unsigned id = 0; id < 520; id++)
    if (key_bit(j->key_physical, id) && !key_valid(layout, id))
      return 0;
  if (key_bit(j->key_text, 0))
    return 0;
  for (unsigned k = 1; k < 256; k++)
    if (key_bit(j->key_text, k)) {
      unsigned ids[3];
      if (juku_keyboard_text_contacts(j->profile, k, ids) < 0)
        return 0;
    }
  uint8_t next[65];
  key_effective(j->profile, j->key_physical, j->key_text, next);
  if (memcmp(next, j->key_effective, 65) || j->key_repeat_fraction > 2)
    return 0;
  if (j->key_repeat &&
      (layout != 2 || j->key_repeat > 513 ||
       !key_bit(next, j->key_repeat - 1) || !key_repeatable(j->key_repeat - 1)))
    return 0;
  return 1;
}
