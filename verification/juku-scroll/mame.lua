-- Physical contacts, scheduled in emulated time independently of guest IRQs.
local prefix=assert(os.getenv('JUKU_SCROLL_PREFIX'))
local schedule={}
for line in io.lines(assert(os.getenv('JUKU_SCROLL_KEYS'))) do
 local t,k,d=line:match('(%d+)%s+(%x+)%s+(%d+)');assert(t)
 schedule[#schedule+1]={tonumber(t)/1000,tonumber(k,16),tonumber(d)}
end
local from=tonumber(os.getenv('JUKU_SCROLL_FROM') or '15')
local machine=manager.machine
local cpu=machine.devices[':maincpu']
local screen=machine.screens[':screen']
local events=assert(io.open(prefix..'.events.csv','w'))
local samples=assert(io.open(prefix..'.samples.csv','w'))
events:write('kind,seconds,address,value,pc\n');samples:write('seconds,pc,sp,a,scroll_flag,escape_flag,parsed_drive\n')
local function field(tag,mask)
 for _,f in pairs(machine.ioport.ports[tag].fields) do if f.mask==mask then return f end end
 error('missing contact '..tag)
end
local letters={a={5,32},b={4,2},c={6,2},d={6,32},e={6,8},f={2,32},g={4,32},h={0,32},i={14,8},j={7,32},k={14,32},l={13,32},m={7,2},n={0,2},o={13,8},p={12,8},q={5,8},r={2,8},s={1,32},t={4,8},u={7,8},v={2,2},w={1,8},x={1,2},y={0,8},z={5,2}}
local special={[0x83]={0,1},[0x87]={3,1},[0x88]={5,1},[0x89]={6,1},[27]={3,16},[13]={8,32},[58]={10,32},[59]={11,2},[32]={11,4},[46]={13,2}}
local digits={{12,16},{5,16},{1,16},{6,16},{2,16},{4,16},{0,16},{7,16},{14,16},{13,16}}
if os.getenv('JUKU_JUSS_CONTACTS') then
 for _,r in ipairs({{'qwertyuiop',1,4},{'asdfghjkl',1,8},{'zxcvbnm',0,16}}) do
  for i=1,#r[1] do letters[r[1]:sub(i,i)]={r[2]+i-1,r[3]} end
 end
 for i=1,9 do digits[i+1]={i+1,2} end;digits[1]={11,2}
 special[13]={13,8};special[46]={8,16};special[32]={3,32}
end
local juss=os.getenv('JUKU_JUSS_CONTACTS') ~= nil
local juss_contact=nil
local juss_col=0
local active={}
local function release() juss_contact=nil; for _,f in ipairs(active) do f:clear_value() end;active={} end
local function press(k)
 release();local shift=false;local ctrl=false;local c
 if special[k] then c=special[k]
 elseif k>=1 and k<=26 then c=letters[string.char(k+96)];ctrl=true
 elseif k>=48 and k<=57 then c=digits[k-47]
 elseif k>=65 and k<=90 then c=letters[string.char(k+32)];shift=true
 else c=letters[string.char(k)] end
 assert(c,'unmapped key '..k)
 if juss then
  assert(not ctrl,'JUSS control key is outside this probe')
  local row=0;local mask=c[2];while mask>1 do row=row+1;mask=mask>>1 end
  juss_contact={c[1],row,shift};return
 end
 active[#active+1]=field(':COL.'..c[1],c[2])
 if shift then active[#active+1]=field(':SPECIAL',64) end
 if ctrl then active[#active+1]=field(':SPECIAL',128) end
 for _,f in ipairs(active) do f:set_value(1) end
end
local function log(kind,a,d)
 events:write(string.format('%s,%.9f,%04x,%02x,%04x\n',kind,machine.time:as_double(),a,d,cpu.state.PC.value))
end
local taps={cpu.spaces.io:install_write_tap(0x10,0x17,'video',function(a,d) log('IW',a,d) end),cpu.spaces.io:install_read_tap(5,5,'keyboard',function(a,d) log('IR',a,d) end)}
if juss then
 -- Some JUSS contacts are unused in MAME's fixed Juku input-port definition.
 -- Supply the encoded physical keyboard lines, preserving the DIP-switch bits.
 taps[#taps+1]=cpu.spaces.io:install_write_tap(4,4,'juss-column',function(a,d) juss_col=d&15 end)
 taps[#taps+1]=cpu.spaces.io:install_read_tap(5,5,'juss-contacts',function(a,d)
  if not juss_contact then return d end
  local c=juss_contact
  return (d&0x30)|0x80|(c[3] and 0 or 0x40)|(juss_col==c[1] and ((~c[2]&7)<<1) or 15)
 end)
end
local index=1;local n=0
local frame_subscription=emu.add_machine_frame_notifier(function()
 local t=machine.time:as_double()
 while schedule[index] and t>=schedule[index][1] do
  local e=schedule[index];if e[3]==0 then release() else press(e[2]) end
  log('KEY',e[2],e[3]);index=index+1
 end
end)
emu.register_frame_done(function()
 n=n+1;local t=machine.time:as_double()
 samples:write(string.format('%.9f,%04x,%04x,%02x,%02x,%02x,%02x\n',t,cpu.state.PC.value,cpu.state.SP.value,cpu.state.A.value,cpu.spaces.program:read_u8(0xd499),cpu.spaces.program:read_u8(0xd49a),cpu.spaces.program:read_u8(0xbbf0)))
 if t>=from then screen:snapshot(string.format('%s-%06d.png',prefix,n)) end
end,'frame')
local stop_subscription=emu.add_machine_stop_notifier(function()
 local f=assert(io.open(prefix..'.ram','wb'));f:write(cpu.spaces.program:read_range(0,65535,8));f:close();events:close();samples:close()
end)
-- Subscription/tap objects unsubscribe on collection; retain them for the run.
_G.juku_scroll={taps=taps,frame=frame_subscription,stop=stop_subscription}
