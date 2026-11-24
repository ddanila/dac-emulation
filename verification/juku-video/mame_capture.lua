-- MAME 0.289: -autoboot_delay 0 -autoboot_script <this file>
-- JUKU_CAPTURE_PREFIX must name an existing output directory plus file stem.
local prefix = assert(os.getenv("JUKU_CAPTURE_PREFIX"), "set JUKU_CAPTURE_PREFIX")
local n = 0
emu.register_frame_done(function()
    n = n + 1
    if n == 150 then
        local screen = manager.machine.screens[":screen"]
        screen:snapshot(prefix .. ".png")
        local file = assert(io.open(prefix .. ".json", "w"))
        file:write(string.format('{"width":%d,"height":%d,"capture_frame":%d}\n', screen.width, screen.height, n))
        file:close()
    end
end, "frame")
