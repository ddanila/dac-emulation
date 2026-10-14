"""Small native binding; no duplicate CPU, device or reset implementation."""

import ctypes as C
from pathlib import Path

PROFILES = {
    "juku": {
        "kind": 0,
        "step": "instruction",
        "trace": "logical-access",
        "clock_hz": 2000000,
    },
    "robotron1715m": {
        "kind": 2,
        "step": "clock",
        "trace": "mapped-access",
        "clock_hz": 3993600,
    },
}
SPACES = {"ram": 1, "rom": 2, "video": 3}


class Observation(C.Structure):
    _fields_ = [("cycles", C.c_uint64)] + [
        (n, C.c_uint32) for n in ("pc", "sp", "halted", "bank")
    ]


class Event(C.Structure):
    _fields_ = [
        ("kind", C.c_char_p),
        ("address", C.c_uint32),
        ("data", C.c_uint8),
        ("cycle", C.c_uint64),
        ("source", C.c_uint),
        ("master", C.c_uint),
        ("space", C.c_uint),
        ("offset", C.c_uint32),
    ]


Callback = C.CFUNCTYPE(None, C.c_void_p, C.POINTER(Event))


class Sink(C.Structure):
    _fields_ = [
        ("emit", Callback),
        ("user", C.c_void_p),
        ("count", C.c_uint64),
        ("limit", C.c_uint64),
    ]


class Runtime:
    def __init__(self, library, machine, trace_limit=0):
        self.profile = PROFILES[machine]
        self.library = Path(library).resolve()
        self.lib = C.CDLL(str(self.library))
        try:
            abi = self.lib.dac_verification_abi
        except AttributeError as error:
            raise RuntimeError("runtime lacks verification ABI") from error
        abi.restype, abi.argtypes = C.c_uint, []
        if abi() != 1:
            raise RuntimeError("unsupported verification ABI")
        self.lib.dac_runtime_build_id.restype = C.c_char_p
        self.lib.dac_runtime_build_id.argtypes = []
        self.build_id = self.lib.dac_runtime_build_id().decode("ascii")
        signatures = {
            "dac_create": (C.c_void_p, [C.c_uint]),
            "dac_destroy": (None, [C.c_void_p]),
            "dac_load": (C.c_int, [C.c_void_p, C.c_uint, C.c_void_p, C.c_size_t]),
            "dac_mount_unit": (
                C.c_int,
                [C.c_void_p, C.c_uint, C.c_void_p, C.c_size_t, C.c_int],
            ),
            "dac_power": (C.c_int, [C.c_void_p, C.c_int]),
            "dac_reset": (C.c_int, [C.c_void_p]),
            "dac_run": (C.c_uint, [C.c_void_p, C.c_uint]),
            "dac_key": (C.c_int, [C.c_void_p, C.c_uint, C.c_int]),
            "dac_observe": (C.c_int, [C.c_void_p, C.POINTER(Observation)]),
            "dac_peek": (
                C.c_int,
                [C.c_void_p, C.c_uint, C.c_uint32, C.c_void_p, C.c_size_t],
            ),
            "dac_set_trace": (C.c_int, [C.c_void_p, C.POINTER(Sink)]),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(self.lib, name)
            fn.restype, fn.argtypes = result, args
        self.session = self.lib.dac_create(self.profile["kind"])
        if not self.session:
            raise RuntimeError("cannot create machine")
        self.events, self.epoch, self.overflow = [], 0, False
        self.callback = Callback(self._event)
        self.trace_limit = trace_limit
        if trace_limit:
            sink = Sink(self.callback, None, 0, 0)
            self.checked("dac_set_trace", C.byref(sink))

    def checked(self, name, *args):
        result = getattr(self.lib, name)(self.session, *args)
        if result < 0:
            raise RuntimeError(f"{name} rejected operation ({result})")
        return result

    def _event(self, _, pointer):
        if len(self.events) >= self.trace_limit:
            self.overflow = True
            return
        e = pointer.contents
        self.events.append(
            {
                "epoch": self.epoch,
                "kind": e.kind.decode("ascii"),
                **{
                    n: getattr(e, n)
                    for n in (
                        "address",
                        "data",
                        "cycle",
                        "source",
                        "master",
                        "space",
                        "offset",
                    )
                },
            }
        )

    def load(self, slot, data):
        self.checked("dac_load", slot, data, len(data))

    def mount(self, unit, data, writable=False):
        self.checked("dac_mount_unit", unit, data, len(data), int(writable))

    def power(self):
        self.checked("dac_power", 1)

    def reset(self):
        self.checked("dac_reset")
        self.epoch += 1

    def run(self, budget):
        if type(budget) is not int or not 1 <= budget <= 100000:
            raise ValueError("run slice must be 1..100000 clocks")
        actual = self.lib.dac_run(self.session, budget)
        if self.overflow:
            raise RuntimeError("trace limit exceeded; trace is incomplete")
        if not actual:
            raise RuntimeError("machine made no progress")
        return actual

    def observe(self):
        out = Observation()
        self.checked("dac_observe", C.byref(out))
        return {name: getattr(out, name) for name, _ in out._fields_}

    def peek(self, space, address, length):
        if (
            space not in SPACES
            or type(address) is not int
            or not 0 <= address <= 0xFFFFFFFF
        ):
            raise ValueError("invalid memory space/address")
        if type(length) is not int or not 0 <= length <= 262144:
            raise ValueError("invalid memory length")
        out = C.create_string_buffer(length)
        self.checked("dac_peek", SPACES[space], address, out, length)
        return out.raw

    def close(self):
        if self.session:
            self.lib.dac_destroy(self.session)
            self.session = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
