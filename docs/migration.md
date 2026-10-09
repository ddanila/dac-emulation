# Migration sequence

## 1. Establish the repository

Create this public MIT-licensed scaffold, document ownership and the intended interface, and keep existing Juku repositories operational. This stage introduces no emulator implementation or new dependency for existing projects.

## 2. Extract Juku incrementally

Implementation is present; bounded native comparisons pass. Full HDL qualification is deferred, and inherited structural-HDL/automatic-PTY failures remain documented in [the extraction report](juku-extraction.md). Consumers have not switched.

Before moving code, record source commits, relevant licenses, and the current regression results. Preserve authorship and source lineage. Extract shared tracing and parameterized media storage in small changes, then separate machine state and execution from the native harness.

Keep a compatibility runner for existing command-line options, environment variables, output artifacts, and PTY behavior. Avoid changing hardware behavior in the same change as moving code. Do not keep two independently maintained copies after the transition.

Acceptance requires the relevant existing Juku boot, framebuffer, typed bus-event, disk, serial, and operating-system integration checks to pass against the extracted implementation. Compare bounded scenarios with the recorded baseline. Run required checks on the native platforms supported by the existing workflows.

## 3. Switch the Juku consumer

Once extraction passes, make `8080-cosim` pin the canonical core here. Retain board models, HDL, physical evidence, and co-simulation harnesses in `8080-cosim`. Keep the existing sibling-checkout and smoke-kit workflows working through the compatibility runner before migrating consumers to explicit executable or artifact selection.

`juku-common` remains the shared guest-software repository. No repository rename is required.

## 4. Implement VJUGA and Robotron 1715M

VJUGA already exists in the source hardware repository, with Z80 and adapted BIOS. Select one shared software Z80 dependency for VJUGA and Robotron; retain distinct board models.

Build up CPU/reset/ROM/banked memory, timers and interrupts, serial keyboard, DMA and floppy control, then video. Reuse a tested Z80 core with a compatible license. Use pinned MAME runs for differential evidence and physical-machine observations to resolve discrepancies.

The first end-to-end milestone is a reproducible original-system boot to an interactive prompt with working keyboard and disk operations. Record known approximations explicitly.

## 5. Connect browser exhibits

Build the same cores for WebAssembly and implement the browser runner. Verify that bounded execution keeps the UI responsive, video buffers have explicit ownership, and losing focus releases keys. Connect the machine interface to DAC's power controls, keyboard, monitor surface, and available indicators.

Publish versioned emulator artifacts for the museum to pin. Decide artifact delivery and large-model storage separately from this source layout.
