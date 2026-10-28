# Selected ADC trace source binding

The retained cfunc.mod and interface specification regenerate the exact C source used for the selected ADC object. Recompiling with the selected preprocessing tool and available matching ngspice headers produces a byte-identical cfunc.o. Its hash matches the ADC object recorded as linked into the selected startup-fixes digital.cm. Commands, header hashes, generated source, object and selected build receipt are retained.

ROBOTRON_ADC_TRACE occurs once, guarding only cm_message_printf in the normal single-bit EVENT branch when the sampled digital result differs from stored output. The log precedes output assignment and delay handling. It is a sampled threshold-decision log, not an exact analog crossing or a complete analog-step/rejection history. Multi-bit conversion returns through another branch; hysteresis can suppress an unknown decision later. The bounded board uses equal-width, non-hysteretic converters. Source binding does not establish logging equivalence or convergence; complete waveform and firmware controls are separate.

Two initial local setup attempts used stale include directories and failed before compilation; the fresh retained build uses the available headers and proves byte equality against the original object.
