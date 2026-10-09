# Differential tests

`legacy_compare.py SOURCE BASELINE CANDIDATE --report build/comparison.json` compares bounded runs of the independently compiled original and extracted native binaries. It checks RAM, state, framebuffer, typed bus/read traces, and stdout/stderr byte for byte, recording source commit and artifact hashes. ROMs/disks are borrowed from SOURCE, never copied into this repository.

`vjuga_compare.py SOURCE` is an optional slow tv80 boot/framebuffer comparison in both decode modes, preserving the existing compatible-subset oracle. It is not part of `make test`, and its full run was deferred during extraction. See [validation](../../docs/juku-extraction.md).
