static void keyboard_contacts_test(void) {
  juku *j = juku_create();
  assert(j);
  assert(!juku_keyboard_contact(j, 5 * 8 + 3, 1)); /* Q */
  assert(!juku_keyboard_contact(j, 5 * 8 + 5, 1)); /* A wins encoder */
  j->kbd_col = 5;
  assert((j->cpu.port_in(j, 5) & 15) == 4);
  assert(!juku_keyboard_contact(j, 5 * 8 + 5, 0));
  assert((j->cpu.port_in(j, 5) & 15) == 8);
  assert(!juku_keyboard_contact(j, 128, 1));
  assert(!juku_key(j, 'A', 1));
  assert(!juku_key(j, 'A', 0));
  assert(!(j->cpu.port_in(j, 5) & 64)); /* physical Shift survives text up */
  assert(!juku_keyboard_contact(j, 129, 1));
  assert(!(j->cpu.port_in(j, 5) & 128));
  assert(!juku_keyboard_release_all(j));
  assert((j->cpu.port_in(j, 5) & 0xcf) == 0xcf);
  assert(juku_keyboard_contact(j, 7, 1) == -EINVAL);
  assert(juku_keyboard_state_valid(j));
  j->kbd_col = 255;
  assert(!juku_keyboard_state_valid(j));
  juku_destroy(j);
  j = juku_create();
  assert(!juku_set_profile(j, 5));
  assert(!juku_key(j, 'A', 1));
  assert(j->at_count == 2 && j->at_queue[0] == 42 && j->at_queue[1] == 30);
  assert(!juku_key(j, 'B', 1));
  assert(j->at_count == 3 && j->at_queue[2] == 48);
  assert(!juku_key(j, 'A', 0));
  assert(j->at_count == 4 && j->at_queue[3] == 158);
  assert(!juku_key(j, 'z', 0));
  assert(j->at_count == 4); /* unrelated release */
  assert(!juku_key(j, 'B', 1));
  assert(j->at_count == 4); /* browser repeat ignored */
  j->at_count = 0;
  j->cpu.cyc = j->key_repeat_due - 1;
  juku_step_devices(j);
  assert(!j->at_count);
  j->cpu.cyc++;
  juku_step_devices(j);
  assert(j->at_count == 1 && j->at_queue[0] == 48);
  unsigned long repeat_start = j->cpu.cyc;
  for (unsigned i = 0; i < 3; i++) {
    j->cpu.cyc = j->key_repeat_due;
    juku_step_devices(j);
  }
  assert(j->cpu.cyc - repeat_start == 550000);
  j->at_count = 1;
  assert(!juku_key(j, 'B', 0));
  assert(!j->key_repeat && j->at_count == 3);
  assert(j->at_queue[1] == 176 && j->at_queue[2] == 170);
  j->at_count = 0;
  assert(!juku_keyboard_contact(j, 0x11d, 1));
  assert(j->at_count == 2 && j->at_queue[0] == 0xe0 && j->at_queue[1] == 29);
  assert(!juku_keyboard_release_all(j));
  assert(j->at_count == 4 && j->at_queue[3] == 157);
  j->at_count = sizeof j->at_queue - 1;
  assert(juku_key(j, 'A', 1) == -EAGAIN);
  assert(!j->key_text['A' / 8] && !j->key_repeat);
  j->at_count = 0;
  assert(!juku_key(j, 'A', 1));
  j->at_count = sizeof j->at_queue;
  unsigned long due = j->key_repeat_due;
  j->cpu.cyc = due;
  juku_step_devices(j);
  assert(j->at_count == sizeof j->at_queue);
  j->at_count = 0;
  j->cpu.cyc++;
  juku_step_devices(j);
  assert(!j->at_count); /* no catch-up burst */
  assert(!juku_keyboard_release_all(j));
  assert(juku_keyboard_state_valid(j));
  juku_destroy(j);
}
static void keyboard_snapshot_test(void) {
  for (unsigned profile = 0; profile < JUKU_PROFILE_COUNT; profile++) {
    dac_session *s = dac_create(0);
    uint8_t rom[16384] = {0xc3, 0, 0};
    assert(!dac_juku_set_profile(s, profile));
    assert(!dac_load(s, 0, rom, sizeof rom));
    assert(!dac_power(s, 1));
    assert(!dac_key(s, 'A', 1));
    assert(!dac_keyboard_contact(s, profile == 5 ? 29 : 129, 1));
    dac_run(s, 10000);
    size_t n = dac_state_size(s);
    void *saved = malloc(n), *expected = malloc(n), *actual = malloc(n);
    assert(!dac_state_save(s, saved, n));
    dac_run(s, 1200000);
    assert(!dac_keyboard_release_all(s));
    assert(!dac_state_save(s, expected, n));
    assert(!dac_state_load(s, saved, n));
    dac_run(s, 1200000);
    assert(!dac_keyboard_release_all(s));
    assert(!dac_state_save(s, actual, n));
    assert(!memcmp(expected, actual, n));
    free(saved);
    free(expected);
    free(actual);
    dac_destroy(s);
  }
}
