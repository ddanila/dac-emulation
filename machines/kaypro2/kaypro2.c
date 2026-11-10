/* SPDX-License-Identifier: MIT
 * Kaypro II/4 81-240A headless profile. SIO polling/FIFO and timed TX adapted
 * from machines/robotron1715/peripherals.h; source references in README.md.
 * No floppy, interrupts, synchronous SIO, or electrical waveform claim.
 */
#include "kaypro2.h"
#include <errno.h>
#include <string.h>
static void trace(kaypro2 *m,const char *kind,uint16_t a,uint8_t v,unsigned space){
    dac_trace_access(&m->trace,kind,a,v,m->cpu.cycles,4,DAC_MASTER_CPU,space,a);
}
uint8_t kaypro2_read(void *p,uint16_t a){
    kaypro2 *m=p;uint8_t v;unsigned space=DAC_SPACE_RAM;
    if((m->system&128)&&a<0x3000){v=a<4096?m->rom[a]:0xff;space=DAC_SPACE_ROM;}
    else if((m->system&128)&&a<0x4000){v=m->video[a-0x3000];space=DAC_SPACE_RAM;}
    else v=m->ram[a];
    trace(m,"MR",a,v,space);return v;
}
void kaypro2_write(void *p,uint16_t a,uint8_t v){
    kaypro2 *m=p;
    if((m->system&128)&&a<0x3000)return; /* no underlying RAM write */
    if((m->system&128)&&a<0x4000)m->video[a-0x3000]=v;
    else m->ram[a]=v;
    trace(m,"MW",a,v,DAC_SPACE_RAM);
}
unsigned kaypro2_baud(const kaypro2 *m,unsigned n){
    static const unsigned rates10[16]={500,750,1100,1345,1500,3000,6000,12000,18000,20000,24000,36000,48000,72000,96000,192000};
    static const unsigned div[4]={1,16,32,64};
    if(n>1)return 0;
    return rates10[m->baud[n]&15]*16/(10*div[m->sio[n].wr[4]>>6]);
}
unsigned kaypro2_character_ticks(const kaypro2 *m,unsigned n){
    static const unsigned bits[4]={5,7,6,8};
    if(n>1)return 0;
    unsigned baud=kaypro2_baud(m,n),stop=(m->sio[n].wr[4]>>2)&3;
    if(!baud||!stop)return 0;
    unsigned half=2+2*bits[(m->sio[n].wr[5]>>5)&3]+((m->sio[n].wr[4]&1)?2:0)+(stop==1?2:stop==2?3:4);
    return (KAYPRO2_CLOCK_HZ*half+2*baud-1)/(2*baud);
}
int kaypro2_receive(kaypro2 *m,unsigned n,uint8_t v){
    if(n>1)return -EINVAL;
    kaypro2_sio *s=&m->sio[n];
    if(!(s->wr[3]&1))return -EAGAIN;
    if(s->count==3){s->errors|=0x20;return -ENOSPC;}
    s->fifo[s->count++]=v;return 0;
}
static uint8_t sio_read(kaypro2 *m,unsigned port){
    kaypro2_sio *s=&m->sio[port&1];uint8_t v;
    if(!(port&2)){v=s->count?s->fifo[0]:0;if(s->count){--s->count;memmove(s->fifo,s->fifo+1,s->count);}return v;}
    unsigned reg=s->pointer;s->pointer=0;
    return reg==0?(s->count?1:0)|(s->holding?0:4)|0x28:reg==1?s->errors|(!s->shifting?1:0):0;
}
static void sio_write(kaypro2 *m,unsigned port,uint8_t v){
    unsigned n=port&1;kaypro2_sio *s=&m->sio[n];
    if(!(port&2)){
        unsigned ticks=kaypro2_character_ticks(m,n);
        if(!(s->wr[5]&8)||!ticks||s->holding)return;
        if(!s->shifting){s->data=v;s->shifting=1;s->due=m->cpu.cycles+ticks;}
        else{s->next=v;s->holding=1;}return;
    }
    if(s->pointer){s->wr[s->pointer]=v;s->pointer=0;return;}
    if(((v>>3)&7)==3){memset(s,0,sizeof(*s));return;}
    if(((v>>3)&7)==6)s->errors=0;
    s->pointer=v&7;
}
static uint8_t input(void *p,uint16_t address){
    kaypro2 *m=p;unsigned a=address&0x9f;
    if(!m->io_active){
        m->io_active=1;m->io_value=0xff;
        if(a>=4&&a<=7)m->io_value=sio_read(m,a);
        else if(a==0x1c)m->io_value=(m->system&~8u)|0x80;
        else m->unclaimed_io++;
        trace(m,"IR",address,m->io_value,DAC_SPACE_IO);
    }return m->io_value;
}
static void output(void *p,uint16_t address,uint8_t v){
    kaypro2 *m=p;unsigned a=address&0x9f;if(m->io_active)return;m->io_active=1;
    trace(m,"IW",address,v,DAC_SPACE_IO);
    if(a<4)m->baud[0]=v&15;
    else if(a<8)sio_write(m,a,v);
    else if(a>=12&&a<=15)m->baud[1]=v&15;
    else if(a==0x1d){
        if(m->pio_expect_mask){m->pio_mask=v;m->pio_expect_mask=0;}
        else if((v&15)==15){m->pio_mode=v>>6;m->pio_expect_mask=m->pio_mode==3;}
    }
    else if(a==0x1c)m->system=v;
    else m->unclaimed_io++;
}
void kaypro2_reset(kaypro2 *m){
    m->system=0x80;m->pio_mode=1;m->pio_mask=255;m->pio_expect_mask=0;
    m->baud[0]=m->baud[1]=5;m->io_active=0;m->unclaimed_io=0;
    memset(m->sio,0,sizeof m->sio);
    dac_z80_init(&m->cpu,(dac_z80_bus){m,kaypro2_read,kaypro2_write,input,output,NULL});
}
void kaypro2_init(kaypro2 *m){memset(m,0,sizeof(*m));kaypro2_reset(m);}
int kaypro2_load(kaypro2 *m,const void *p,size_t n){
    if(!p||n!=sizeof m->rom)return -EINVAL;
    if(m->cpu.cycles)return -EBUSY;
    memcpy(m->rom,p,n);return 0;
}
void kaypro2_run(kaypro2 *m,unsigned ticks){
    while(ticks--){
        for(unsigned n=0;n<2;n++){
            kaypro2_sio *s=&m->sio[n];
            if(s->shifting&&m->cpu.cycles>=s->due){
                if(m->transmit)m->transmit(m->serial_user,n,s->data);
                if(s->holding){s->data=s->next;s->holding=0;s->due+=kaypro2_character_ticks(m,n);}
                else s->shifting=0;
            }
        }
        dac_z80_tick(&m->cpu,0,0);
        if(!(m->cpu.pins&Z80_IORQ))m->io_active=0;
    }
}
