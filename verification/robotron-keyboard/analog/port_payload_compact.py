#!/usr/bin/env python3
"""Reconstruct exact dense port payloads from compact serialized log bodies."""
from scope_metadata_compact import Decoder
from port_payload import parse


class PortDecoder(Decoder):
    def __init__(self):
        super().__init__()
        self.tag='VPPD';self.dense='VPP';self.parser=parse
