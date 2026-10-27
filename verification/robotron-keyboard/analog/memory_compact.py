"""Strict reconstruction of native memory metadata from compact log records."""
from scope_metadata_compact import Decoder
from memory_metadata import parse

class MemoryDecoder(Decoder):
    def __init__(self):
        super().__init__();self.tag='VMMD';self.dense='VMM';self.parser=parse
