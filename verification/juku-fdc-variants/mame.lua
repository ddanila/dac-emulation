dofile(assert(os.getenv('JUKU_VARIANT_SCHEDULER')))
local events=assert(io.open(assert(os.getenv('JUKU_SCROLL_PREFIX'))..'.fdc.csv','w'))
events:write('seconds,port,value\n')
local cpu=manager.machine.devices[':maincpu']
local tap=cpu.spaces.io:install_write_tap(0x1c,0x1f,'fdc-variant',function(a,d)
 events:write(string.format('%.9f,%02x,%02x\n',manager.machine.time:as_double(),a,d))
end)
local stop=emu.add_machine_stop_notifier(function() events:close() end)
_G.juku_variant={tap=tap,stop=stop}
