dofile(assert(os.getenv('JUKU_COMPARISON_SCHEDULER')))
local ram=assert(manager.machine.memory.shares[':ram'])
local prefix=assert(os.getenv('JUKU_SCROLL_PREFIX'))
local stop=emu.add_machine_stop_notifier(function()
 local f=assert(io.open(prefix..'.physical.ram','wb'))
 for a=0,65535 do f:write(string.char(ram:read_u8(a))) end
 f:close()
end)
_G.juku_comparison={stop=stop}
