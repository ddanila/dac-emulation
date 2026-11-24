-- Reuse the physical-contact scheduler; only this diagnostic can correct an application operand.
dofile(assert(os.getenv('JUKU_FONT_SCHEDULER')))
local machine=manager.machine
local cpu=machine.devices[':maincpu']
local ram=assert(machine.memory.shares[':ram'])
local prefix=assert(os.getenv('JUKU_SCROLL_PREFIX'))
local control=tonumber(os.getenv('JUKU_FONT_OPERAND') or '0')
local trace=assert(io.open(prefix..'.trace.csv','w'))
trace:write('kind,seconds,address,value,pc\n')
local function log(kind,a,d)
 trace:write(string.format('%s,%.9f,%04x,%02x,%04x\n',kind,machine.time:as_double(),a,d,cpu.state.PC.value))
end
local taps={
 cpu.spaces.program:install_read_tap(0xdd00,0xe061,'font-source',function(a,d)
  if cpu.state.PC.value<0xb200 and machine.time:as_double()>16 then log('READ',a,d) end
 end),
 cpu.spaces.program:install_write_tap(0xd7fb,0xd7fc,'font-pointer',function(a,d)
  log('FONT',a,d)
  if control~=0 and ram:read_u8(control-1)==0x21 and ram:read_u8(control)==1 and ram:read_u8(control+1)==0xdd then
   ram:write_u8(control,2);log('PATCH',control,2)
  end
 end)
}
local stop=emu.add_machine_stop_notifier(function()
 local f=assert(io.open(prefix..'.physical.ram','wb'))
 for a=0,65535 do f:write(string.char(ram:read_u8(a))) end
 f:close();trace:close()
end)
_G.juku_fonts={taps=taps,stop=stop}
