-- Reuse physical keyboard scheduling and final screen capture from issue 20.
dofile(assert(os.getenv('JUKU_SCROLL_SCRIPT')))
local cpu=manager.machine.devices[':maincpu']
local f=assert(io.open(assert(os.getenv('JUKU_SCROLL_PREFIX'))..'.fdc.csv','w'))
f:write('seconds,pc,op,reg,value\n')
local function log(op,a,d)
 f:write(string.format('%.9f,%04x,%s,%02x,%02x\n',manager.machine.time:as_double(),cpu.state.PC.value,op,a,d))
end
_G.juku_fdc_probe={
 cpu.spaces.io:install_read_tap(0x1c,0x1f,'fdc_read',function(a,d) log('read',a,d) end),
 cpu.spaces.io:install_write_tap(0x1c,0x1f,'fdc_write',function(a,d) log('write',a,d) end),
 emu.add_machine_stop_notifier(function() f:close() end)
}
