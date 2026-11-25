-- Configure the external region explicitly, then let the real CPU do all accesses.
local cpu=manager.machine.devices[':maincpu']
local ram=manager.machine.memory.shares[':ram']
local cart=manager.machine.memory.regions[':expcart']
local kind=assert(os.getenv('JUKU_WINDOW_CART'))
if kind~='stock' then
 for a=0,0x7fff do cart:write_u8(a,255) end
 if kind~='-' then
  local f=assert(io.open(kind,'rb')); local bytes=f:read('*a');f:close()
  for i=1,#bytes do cart:write_u8(i-1,bytes:byte(i)) end
 end
end
local f=assert(io.open(assert(os.getenv('JUKU_WINDOW_PROGRAM')),'rb'))
local bytes=f:read('*a');f:close()
for a=0,65535 do ram:write_u8(a,0) end
for i=1,#bytes do ram:write_u8(0xc100+i-1,bytes:byte(i)) end
cpu.state['PC'].value=0xc100
local finished=false
emu.register_frame_done(function()
 if not finished and ram:read_u8(0xc8ff)==0xd3 then
  finished=true
  local out=assert(io.open(assert(os.getenv('JUKU_WINDOW_OUTPUT')),'wb'))
  for a=0,65535 do out:write(string.char(ram:read_u8(a))) end
  out:close();manager.machine:exit()
 end
end)
