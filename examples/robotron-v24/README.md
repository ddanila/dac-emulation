
`python3 build-tx.py` also builds DACTX.COM, the original MIT reverse-direction
sender. In DAC select Receive XMODEM file from guest, then run `DACTX NAME.EXT`.
It opens an existing CP/M file, transmits 128-byte records at 1200 8N1, retries
rejected/timed-out blocks and closes the file. The browser download preserves
record padding; XMODEM checksum has no original-byte-length field. The optional
transfer qualification checks a binary round trip through both COM programs.
