use std::{env, fs};
use juku::Machine;
fn main() {
    let a: Vec<String> = env::args().collect();
    assert_eq!(a.len(),5);
    let mut m=Machine::new(&fs::read(&a[1]).unwrap()).unwrap();
    if a[2]!="-" { m.insert_expansion(&fs::read(&a[2]).unwrap()).unwrap(); }
    let program=fs::read(&a[3]).unwrap();
    for (i,b) in program.iter().enumerate() { m.poke(0xc100+i as u16,*b); }
    m.cpu_mut().pc=0xc100;
    while m.ram()[0xc8ff]!=0xd3 && m.cycles()<3000000 { m.step(); }
    assert_eq!(m.ram()[0xc8ff],0xd3,"guest did not finish");
    fs::write(&a[4],m.ram()).unwrap();
}
