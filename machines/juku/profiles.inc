/* Hardware presets are independent of firmware contents and filenames. */
static const juku_profile profiles[JUKU_PROFILE_COUNT] = {
    {"mainboard-juku", "Mainboard FD1793 / Juku", "EKTA #0031, #0037", 1793, 0,
     0},
    {"mainboard-juss", "Mainboard FD1793 / JUSS", "EKTA #0035", 1793, 0, 1},
    {"early-juss", "Mainboard FD1791 / JUSS", "EKTA #0024", 1791, 0, 1},
    {"early-juku", "Mainboard FD1791 / Juku", "Monitor 3.3", 1791, 0, 0},
    {"card-juku", "Expansion FD1793 / Juku", "EKTA #0032", 1793, 1, 0},
    {"card-at", "Expansion FD1793 / AT", "EKTA #0043", 1793, 1, 2},
    {"single-density", "Mainboard FD1792 / JUSS",
     "Generated FM diagnostics; historical pairing unverified", 1792, 0, 1}};
const juku_profile *juku_profile_info(unsigned id) {
  return id < JUKU_PROFILE_COUNT ? &profiles[id] : NULL;
}
unsigned juku_get_profile(const juku *j) { return j ? j->profile : UINT_MAX; }
int juku_set_profile(juku *j, unsigned id) {
  if (!j || id >= JUKU_PROFILE_COUNT)
    return -EINVAL;
  if (j->cpu.cyc)
    return -EBUSY;
  j->profile = id;
  j->fdc_bus_invert = profiles[id].controller != 1793;
  j->fdc.fm_only = profiles[id].controller == 1792;
  j->fdc.fm = j->fdc.fm_only;
  return 0;
}
static void juku_mainboard_control(juku *j) {
  if (j->fdc_enabled && !profiles[j->profile].card) {
    juku_fdc_portc(&j->fdc, j->portc);
    j->fdc.fm = (j->portc >> 4) & 1;
  }
}
static unsigned juku_fdc_base(const juku *j) {
  return profiles[j->profile].card ? 0x30 : 0x1c;
}
static void juku_juss_contact(uint8_t key, int *col, int *row, int *shift,
                              int *ctrl) {
  *col = -1;
  *row = -1;
  *shift = 0;
  *ctrl = 0;
  switch (key) {
  case 0xc4: case 0xe4: *col=11; *row=3; *shift=key==0xc4; return;
  case 0xd5: case 0xf5: *col=12; *row=2; *shift=key==0xd5; return;
  case 0xd6: case 0xf6: *col=10; *row=3; *shift=key==0xd6; return;
  case 0xdc: case 0xfc: *col=11; *row=2; *shift=key==0xdc; return;
  }
  if (key >= 'A' && key <= 'Z') {
    key += 32;
    *shift = 1;
  }
  const char *rows[] = {"1234567890-@\\", "qwertyuiop", "asdfghjkl",
                        "zxcvbnm,./;"};
  const unsigned starts[] = {2, 1, 1, 0};
  for (unsigned r = 0; r < 4; r++) {
    const char *p = strchr(rows[r], key);
    if (p && key) {
      *col = (int)(p - rows[r]) + starts[r];
      *row = r + 1;
      return;
    }
  }
  const char *plain = "1234567890-@\\,./;:";
  const char *upper = "!\"#$%&'()_=`^<>?+*";
  const char *p = strchr(upper, key);
  if (p && key) {
    juku_juss_contact((uint8_t)plain[p - upper], col, row, shift, ctrl);
    *shift = 1;
    return;
  }
  switch (key) {
  case 13:
  case 10:
    *col = 13;
    *row = 3;
    return;
  case 9:
    *col = 0;
    *row = 2;
    return;
  case 8:
    *col = 1;
    *row = 5;
    return;
  case 27:
    *col = 1;
    *row = 1;
    return;
  case ' ':
    *col = 3;
    *row = 5;
    return;
  case ':':
    *col = 12;
    *row = 3;
    return;
  case '[':
  case '{':
    *col = 13;
    *row = 2;
    *shift = key == '{';
    return;
  case ']':
  case '}':
    *col = 14;
    *row = 2;
    *shift = key == '}';
    return;
  case 127:
    *col = 13;
    *row = 0;
    return;
  case 0x80:
    *col = 5;
    *row = 5;
    return;
  case 0x8b:
    *col = 4;
    *row = 5;
    return;
  case 0x8c:
    *col = 1;
    *row = 0;
    return;
  case 0x8d:
    *col = 0;
    *row = 0;
    return;
  default:
    break;
  }
  if (key >= 1 && key <= 26) {
    juku_juss_contact((uint8_t)('a' + key - 1), col, row, shift, ctrl);
    *ctrl = 1;
  }
}
/* #0043 reads translated AT scan-set-1 bytes from an external shift latch:
 * PB7=ready, PB0=LSB; PA5 clocks, PA7 acknowledges/resets the latch.
 * This is the firmware-visible adapter, not an 8042 at PC I/O addresses. */
static void juku_at_enqueue(juku *j, uint8_t b) {
  // Receiving a new byte loads the shift register from its first bit, even
  // if firmware clocked the empty adapter during a disk operation.
  if (!j->at_count)
    j->at_bit = 0;
  if (j->at_count < sizeof(j->at_queue))
    j->at_queue[j->at_count++] = b;
}
static uint8_t juku_at_read(juku *j) {
  unsigned col = j->kbd_col;
  uint8_t dip =
      col >= 8 && !(j->kbd_s21_config & (1u << (15 - col))) ? 0x20 : 0;
  return dip |
         (j->at_count ? (uint8_t)(0x80 | ((j->at_queue[0] >> j->at_bit) & 1))
                      : 0);
}
static void juku_at_write(juku *j, uint8_t v) {
  uint8_t old = j->at_key;
  j->at_key = v;
  if ((v & 0x20) && !(old & 0x20) && j->at_bit < 7)
    j->at_bit++;
  if ((v & 0x80) && !(old & 0x80)) {
    if (j->at_count) {
      memmove(j->at_queue, j->at_queue + 1, --j->at_count);
    }
    j->at_bit = 0;
  }
}
static unsigned juku_at_scan(uint8_t key, unsigned *shift, unsigned *ctrl) {
  static const uint8_t letters[] = {30, 48, 46, 32, 18, 33, 34, 35, 23,
                                    36, 37, 38, 50, 49, 24, 25, 16, 19,
                                    31, 20, 22, 47, 17, 45, 21, 44};
  *shift = *ctrl = 0;
  // #0043's table assigns Õ to set-1 26 and Ü to 27 (opposite Juku positions).
  switch (key) {
  case 0xc4: case 0xe4: *shift=key==0xc4; return 40;
  case 0xd5: case 0xf5: *shift=key==0xd5; return 26;
  case 0xd6: case 0xf6: *shift=key==0xd6; return 39;
  case 0xdc: case 0xfc: *shift=key==0xdc; return 27;
  }
  if (key >= 'A' && key <= 'Z') {
    key += 32;
    *shift = 1;
  }
  if (key >= 'a' && key <= 'z')
    return letters[key - 'a'];
  if (key >= '1' && key <= '9')
    return key - '1' + 2;
  const char *plain = "0-=\t[];'/`\\,./ ";
  const uint8_t scans[] = {11, 12, 13, 15, 26, 27, 39, 40,
                           53, 41, 43, 51, 52, 53, 57};
  const char *p = strchr(plain, key);
  if (p && key)
    return scans[p - plain];
  const char *upper = "!@#$%^&*()_+{}:\"~|<>?";
  p = strchr(upper, key);
  const uint8_t shifted[] = {2,  3,  4,  5,  6,  7,  8,  9,  10, 11, 12,
                             13, 26, 27, 39, 40, 41, 43, 51, 52, 53};
  if (p && key) {
    *shift = 1;
    return shifted[p - upper];
  }
  if (key == 13 || key == 10)
    return 28;
  if (key == 8)
    return 14;
  if (key == 27)
    return 1;
  if (key >= 1 && key <= 26) {
    *ctrl = 1;
    return letters[key - 1];
  }
  return 0;
}
static void juku_at_key(juku *j, uint8_t key, int down) {
  if (j->live_key && (!down || key != j->live_key)) {
    unsigned shift, ctrl, scan = juku_at_scan(j->live_key, &shift, &ctrl);
    if (scan)
      juku_at_enqueue(j, (uint8_t)(scan | 0x80));
    if (shift)
      juku_at_enqueue(j, 0xaa);
    if (ctrl)
      juku_at_enqueue(j, 0x9d);
  }
  if (down && key != j->live_key) {
    unsigned shift, ctrl, scan = juku_at_scan(key, &shift, &ctrl);
    if (shift)
      juku_at_enqueue(j, 0x2a);
    if (ctrl)
      juku_at_enqueue(j, 0x1d);
    if (scan)
      juku_at_enqueue(j, (uint8_t)scan);
  }
}
