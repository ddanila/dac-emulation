#!/usr/bin/env python3
"""Strict reconstruction of complete native parameter payload records."""
from scope_metadata_compact import Decoder
from parameter_payload import parse

class ParameterDecoder(Decoder):
    def __init__(self):
        super().__init__();self.tag='VPMD';self.dense='VPM';self.parser=parse
