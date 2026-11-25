//! Observation adapter for the unmodified sinijarv-juku/juku-emu core.
use std::{env, fs, io::{BufWriter, Write}};
use juku::Machine;
fn contact(m: &mut Machine, k: u8) {
    m.release_all_keys();
    let letters = [(5,5),(4,1),(6,1),(6,5),(6,3),(2,5),(4,5),(0,5),(14,3),(7,5),(14,5),(13,5),(7,1),(0,1),(13,3),(12,3),(5,3),(2,3),(1,5),(4,3),(7,3),(2,1),(1,3),(1,1),(0,3),(5,1)];
    let digits = [12,5,1,6,2,4,0,7,14,13];
    let (col,row) = match k {
        0x83 => (0,0), 0x87 => (3,0), 0x88 => (5,0), 0x89 => (6,0),
        27 => (3,4), 13 => (8,5), 58 => (10,5), 59 => (11,1), 32 => (11,2), 46 => (13,1),
        b'0'..=b'9' => (digits[(k-b'0') as usize],4),
        b'A'..=b'Z' => {m.set_key(0x80,true);letters[(k-b'A') as usize]},
        b'a'..=b'z' => letters[(k-b'a') as usize],
        1..=26 => {m.set_key(0x81,true);letters[(k-1) as usize]},
        _ => panic!("unmapped key {k:02x}"),
    };
    m.set_key(col<<3|row,true);
}
fn main() {
    let a: Vec<String> = env::args().collect();
    assert_eq!(a.len(),7,"ROM DISK PREFIX KEYS END_MS FROM_MS");
    let mut m=Machine::new(&fs::read(&a[1]).unwrap()).unwrap();
    m.insert_disk(0,fs::read(&a[2]).unwrap(),false).unwrap();
    let keys:Vec<(u64,u8,bool)>=fs::read_to_string(&a[4]).unwrap().lines().map(|l|{
        let v:Vec<_>=l.split_whitespace().collect();
        (v[0].parse::<u64>().unwrap()*2000,u8::from_str_radix(v[1],16).unwrap(),v[2]=="1")
    }).collect();
    let end=a[5].parse::<u64>().unwrap()*2000;
    let from=a[6].parse::<u64>().unwrap()*2000;
    let mut events=BufWriter::new(fs::File::create(format!("{}.events.csv",a[3])).unwrap());
    let mut frames=BufWriter::new(fs::File::create(format!("{}.frames.csv",a[3])).unwrap());
    let mut samples=BufWriter::new(fs::File::create(format!("{}.samples.csv",a[3])).unwrap());
    let mut observations=BufWriter::new(fs::File::create(format!("{}.instructions.csv",a[3])).unwrap());
    writeln!(events,"kind,cycle,address,value,pc").unwrap();
    writeln!(frames,"sequence,cycle,width,height,lit_bytes").unwrap();
    writeln!(samples,"cycle,pc,scroll_flag,parsed_drive").unwrap();
    writeln!(observations,"cycle,pc,a,c,e").unwrap();
    m.log_io(true);
    let(mut index,mut seq,mut next)=(0,0,0);
    let(mut waits,mut longest)=(0u64,0u32);
    while m.cycles()<end {
        while index<keys.len() && m.cycles()>=keys[index].0 {
            let (_,key,down)=keys[index];
            if down {contact(&mut m,key)} else {m.release_all_keys()}
            writeln!(events,"KEY,{},{:02x},{},{:04x}",m.cycles(),key,down as u8,m.cpu().pc).unwrap();index+=1;
        }
        let pc=m.cpu().pc;
        if m.cycles()>from && matches!(pc,0xd9df|0xdcd1|0xcd71|0xcd83|0x0dee|0x0df7) {
            let c=m.cpu();writeln!(observations,"{},{:04x},{:02x},{:02x},{:02x}",m.cycles(),pc,c.a,c.c,c.e).unwrap();
        }
        let op=m.peek(pc);
        let port=if matches!(op,0xdb|0xd3) {m.peek(pc.wrapping_add(1))} else {0};
        let elapsed=m.step();
        if matches!(op,0xdb|0xd3) && port==0x1f && elapsed>18 {waits+=1;longest=longest.max(elapsed)}
        if m.cycles()>=next {
            writeln!(samples,"{},{:04x},{:02x},{:02x}",m.cycles(),m.cpu().pc,m.ram()[0xd499],m.ram()[0xbbf0]).unwrap();next+=40000;
        }
        let f=m.frame();
        if f.seq!=seq {
            seq=f.seq;
            if m.cycles()>=from && f.active_w>0 && f.active_h>0 {
                let pic=f.active_picture();let width=f.active_line(0).len()*8;
                writeln!(frames,"{},{},{},{},{}",seq,m.cycles(),width,f.active_h,pic.iter().filter(|&&x|x!=0).count()).unwrap();
                let mut pbm=format!("P4\n{} {}\n",width,f.active_h).into_bytes();pbm.extend(pic.iter().map(|x|x^255));
                fs::write(format!("{}-{:06}.pbm",a[3],seq),pbm).unwrap();
            }
        }
    }
    for (t,p,v) in m.log_io(false) {writeln!(events,"IW,{},{:04x},{:02x},0000",t,p,v).unwrap()}
    fs::write(format!("{}.ram",a[3]),m.ram()).unwrap();
    fs::write(format!("{}.juk",a[3]),m.disk(0).unwrap().data()).unwrap();
    println!("keys={} cycles={} pc={:04x} data_io_waits={} longest_instruction={}",index,m.cycles(),m.cpu().pc,waits,longest);
}
