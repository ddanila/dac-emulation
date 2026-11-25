use std::{env,fs};
use juku::Machine;
fn main(){
 let a:Vec<String>=env::args().collect();let rom=fs::read(&a[1]).unwrap();
 let keys=[(0xe4,11,5),(0xf5,10,3),(0xf6,12,5),(0xfc,11,3),(0xc4,11,5),(0xd5,10,3),(0xd6,12,5),(0xdc,11,3)];
 for (i,(key,col,row)) in keys.into_iter().enumerate(){
  let mut m=Machine::new(&rom).unwrap();m.run_cycles(4000000);
  let code=[0x31,0,0x30,0xcd,0xd3,0xff,0x32,0,0x20,0x3e,0xd3,0x32,1,0x20,0x76];
  for (n,b) in code.iter().enumerate(){m.poke(0x100+n as u16,*b);}
  // The documented TTI ABI requires mode 1/2. Enter it through the PPI.
  for (n,b) in [0x3e,1,0xd3,6,0xc3,0,1].iter().enumerate(){m.poke(0xc100+n as u16,*b);}
  m.poke(0x2001,0);m.cpu_mut().pc=0xc100;
  m.set_key(0x80,i>=4);m.set_key(col<<3|row,true);
  let end=m.cycles()+600000;while m.ram()[0x2001]!=0xd3&&m.cycles()<end{m.step();}
  let value=m.ram()[0x2000];let font=u16::from_le_bytes([m.ram()[0xd7fb],m.ram()[0xd7fc]]);
  print!("{key:02x},{},{value:02x},",if m.ram()[0x2001]==0xd3{1}else{0});
  for n in 0..9{print!("{:02x}",m.peek(font.wrapping_add((value as u16).wrapping_sub(32)*9+n)));}println!();
 }
}
