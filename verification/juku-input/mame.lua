-- Original monitor TTI reads the inputs; no console bytes are injected.
local machine=manager.machine
local cpu=machine.devices[':maincpu']
local ram=machine.memory.shares[':ram']
local mem=cpu.spaces.program
local code={0x31,0,0x30}
for i=0,7 do
 for _,b in ipairs({0xcd,0xd3,0xff,0x32,i,0x20}) do code[#code+1]=b end
end
for _,b in ipairs({0x3e,0xd3,0x32,0x10,0x20,0x76}) do code[#code+1]=b end
for i,b in ipairs(code) do ram:write_u8(0x100+i-1,b) end
for i,b in ipairs({0x3e,1,0xd3,6,0xc3,0,1}) do ram:write_u8(0xc100+i-1,b) end
ram:write_u8(0x2010,0);cpu.state.PC.value=0xc100
local natural=os.getenv('JUKU_INPUT_MODE')=='natural'
if natural then machine.natkeyboard:post('äõöüÄÕÖÜ') end
local function field(tag,mask)
 for _,f in pairs(machine.ioport.ports[tag].fields) do if f.mask==mask then return f end end
 error('missing field '..tag)
end
local contacts={{11,32},{10,8},{12,32},{11,8},{11,32},{10,8},{12,32},{11,8}}
local keys={0xe4,0xf5,0xf6,0xfc,0xc4,0xd5,0xd6,0xdc}
local start=machine.time:as_double();local held={};local previous=-1;local done=false
emu.register_frame_done(function()
 if done then return end
 if not natural then
  local t=machine.time:as_double()-start;local phase=math.floor(t/0.15)
  if phase~=previous then
   for _,f in ipairs(held) do f:clear_value() end;held={};previous=phase
   local i=math.floor(phase/2)+1
   if phase%2==0 and i<=8 then
    held={field(':COL.'..contacts[i][1],contacts[i][2])}
    if i>=5 then held[#held+1]=field(':SPECIAL',64) end
    for _,f in ipairs(held) do f:set_value(1) end
   end
  end
 end
 if ram:read_u8(0x2010)==0xd3 then
  done=true;local out=assert(io.open(assert(os.getenv('JUKU_INPUT_OUTPUT')),'w'))
  local font=ram:read_u8(0xd7fb)+ram:read_u8(0xd7fc)*256
  for i,key in ipairs(keys) do
   local value=ram:read_u8(0x2000+i-1);out:write(string.format('%02x,1,%02x,',key,value))
   for n=0,8 do out:write(string.format('%02x',mem:read_u8(font+(value-32)*9+n))) end
   out:write('\n')
  end
  out:close();machine:exit()
 end
end)
