# Architecture and interface proposal

Status: Juku instances, shared trace/media interfaces, a C build, and the native runner are implemented. The complete museum interface below remains a design outline; current experimental signatures are in `machines/juku/juku.h`.

## Core and host boundary

A machine instance owns its CPU, memory, devices, pending events, and emulated clock. Avoid process-global mutable machine state so tests and museum exhibits can create independent instances.

The core advances in emulated time. It must not sleep, read environment variables, install signal handlers, open terminal devices, or access browser APIs. Host runners supply input and media and decide when to call the core. Native file handling and browser persistence sit behind storage interfaces.

Native tests should run without real-time throttling. Interactive runners pace the same core to the machine's clock. A runner must execute bounded slices and yield regularly; host scheduling delays do not change the order of emulated events.

## Initial machine interface

| Operation | Intended contract |
| --- | --- |
| Create / destroy | Allocate or release all instance-owned resources; return explicit errors for unsupported configurations. |
| Load firmware | Validate machine-required regions and sizes; retain source identity for reproducible tests. |
| Attach / eject media | Supply media through a storage interface with declared format and write policy. Each machine defines supported insertion/ejection behavior. |
| Power on / off | Model the machine's power lifecycle. Power-on initializes a cold machine; power-off stops execution. Media persistence is a separate policy. |
| Reset | Apply the machine's reset behavior, distinct from power cycling or host pause. |
| Run for a bounded interval | Advance emulated time and report time actually consumed and stop reason. Define instruction-boundary overshoot before freezing the API. |
| Key down / up | Accept machine-key identifiers. Host layouts map to these identifiers; focus loss releases held keys. |
| Read video output | Expose dimensions, pixel format, stride, update generation, and buffer lifetime. The host converts output into a 3D monitor texture. |
| Observe status | Expose available indicators and events, such as motor activity; distinguish emulated signals from presentation effects. |

Pause/resume belongs to the runner: pausing stops advancement without resetting the machine. Diagnostic hooks are optional and must not change guest-visible behavior. Complete save states are deferred until each core can serialize all relevant device state and pending events.

## Shared components

**Tracing:** start from Juku's typed memory read/write, I/O read/write, and interrupt-acknowledge events. Make sinks replaceable so native tools can write files while browser builds can disable or buffer diagnostics. Reserve room for source identifiers, explicit address spaces, and optional emulated timestamps. Event-order agreement and timing agreement are separate assertions.

**Media:** separate byte storage and sector metadata from a controller's registers and command execution. Parameterize geometry and sector identifiers; never infer format solely from byte size. Provide a simple raw-sector implementation first. Richer formats and disk overlays should follow actual machine requirements.

**Testing:** share process invocation, bounded-run handling, artifact identity, and comparison diagnostics. Keep hardware expectations and scenario vectors with their machines or devices. Comparisons must state what is being compared and must report skipped coverage explicitly.

## Machine-specific components

Memory maps, ROM overlays, keyboard protocols, interrupt wiring, video generation, and device behavior belong to each machine. The Juku 8080 and WD1772/VG93 models are not Robotron Z80 and 8272-family replacements. Reuse device implementations only where their actual behavior and tested scope fit.

No general-purpose plugin loader, universal bus framework, or stable external ABI is required for Juku, VJUGA, and Robotron. Evolve interfaces using concrete consumers before freezing them.

## Dependencies and reproducibility

Pin imported cores and reference emulators to exact revisions. Record source URLs, original licenses, local changes, build recipes, and firmware/media hashes used by tests. Matching another emulator establishes agreement within a scenario; physical evidence is needed to resolve shared mistakes or claim greater hardware fidelity.
