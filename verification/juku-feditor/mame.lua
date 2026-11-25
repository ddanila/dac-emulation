dofile(assert(os.getenv('JUKU_FEDITOR_SCHEDULER')))
local machine=manager.machine
local cpu=machine.devices[':maincpu']
local ram=assert(machine.memory.shares[':ram'])
local prefix=assert(os.getenv('JUKU_SCROLL_PREFIX'))
local events=assert(io.open(prefix..'.fonts.csv','w'))
events:write('kind,seconds,address,value,pc\n')
local function log(kind,a,d)
 events:write(string.format('%s,%.9f,%04x,%02x,%04x\n',kind,machine.time:as_double(),a,d,cpu.state.PC.value))
end
local taps={cpu.spaces.program:install_read_tap(0xdd00,0xe4ff,'font-read',function(a,d)
 if machine.time:as_double()>16 and cpu.state.PC.value<0xb200 then log('FONTREAD',a,d) end
end),cpu.spaces.program:install_write_tap(0xd7f9,0xd7fe,'font-pointer',function(a,d) log('MW',a,d) end)}
local function dump(ms)
 local f=assert(io.open(prefix..'-'..ms..'.ram','wb'))
 for a=0,65535 do f:write(string.char(ram:read_u8(a))) end
 f:close()
end
local next_ms=28000
local frame=emu.add_machine_frame_notifier(function()
 if machine.time:as_double()*1000>=next_ms then dump(next_ms);next_ms=next_ms+2000 end
end)
local stop=emu.add_machine_stop_notifier(function() events:close() end)
_G.juku_feditor={taps=taps,frame=frame,stop=stop}
