#!/usr/bin/env python3
"""Reconstruct exact registered vector signal payloads from compact logs."""
from scope_metadata_compact import Decoder
from signal_handles import parse as signal_parse


def parse(lines):
    if not lines or not lines[0].startswith('VSA_BEGIN '):raise ValueError('Missing scope signal header')
    return signal_parse([line.replace('VSA_','VSH_',1) for line in lines])


class SignalDecoder(Decoder):
    def __init__(self):
        super().__init__();self.tag='VSAD';self.dense='VSA';self.parser=parse
