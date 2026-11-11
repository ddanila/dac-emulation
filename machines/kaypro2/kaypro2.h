/* SPDX-License-Identifier: MIT */
#ifndef DAC_KAYPRO2_H
#define DAC_KAYPRO2_H
#include "../../common/cpu/z80.h"
#include "../../common/trace/trace.h"
#include <stddef.h>
#define KAYPRO2_CLOCK_HZ 2500000u
typedef struct {
    uint8_t wr[8], pointer, fifo[3], count, errors;
    uint8_t shifting, holding, data, next;
    uint64_t due;
} kaypro2_sio;
typedef struct {
    dac_z80 cpu;
    dac_trace_sink trace;
    uint8_t ram[65536], rom[4096], video[2048], chargen[2048];
    uint8_t system, pio_mode, pio_mask, pio_expect_mask, baud[2];
    uint8_t io_active, io_value, modem[2];
    kaypro2_sio sio[2];
    void *serial_user;
    void (*transmit)(void *, unsigned channel, uint8_t);
    uint64_t unclaimed_io;
} kaypro2;
void kaypro2_init(kaypro2 *);
void kaypro2_reset(kaypro2 *); /* retains RAM, ROM, callback */
int kaypro2_load(kaypro2 *,const void *,size_t);
/* CPU aperture -> physical 2114 byte. A4/A5 alias when A6 is high. */
unsigned kaypro2_video_index(uint16_t address);
int kaypro2_load_chargen(kaypro2 *, const void *, size_t);
/* 560x240 monochrome pixels (0/1), deterministic blink phase supplied by caller. */
void kaypro2_render(const kaypro2 *, uint8_t *pixels, unsigned blink_off);
void kaypro2_run(kaypro2 *,unsigned ticks);
uint8_t kaypro2_read(void *,uint16_t);
void kaypro2_write(void *,uint16_t,uint8_t);
unsigned kaypro2_baud(const kaypro2 *,unsigned channel);
unsigned kaypro2_character_ticks(const kaypro2 *,unsigned channel);
/* Completed-byte seam. Caller must pace independently; no magical queue. */
int kaypro2_receive(kaypro2 *,unsigned channel,uint8_t);
int kaypro2_receive_status(kaypro2 *,unsigned channel,uint8_t,uint8_t errors);
void kaypro2_modem(kaypro2 *,unsigned channel,uint8_t rr0_bits);
#endif
