#!/usr/bin/env python3
import ctypes
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


class FilterModel(ctypes.Structure):
    _fields_ = [
        ("prime", ctypes.c_uint32),
        ("a", ctypes.c_uint32),
        ("h2", ctypes.c_uint32),
        ("e", ctypes.c_uint32),
        ("ch", ctypes.c_uint32),
        ("eh", ctypes.c_uint32),
        ("a2", ctypes.c_uint32),
        ("ch_a", ctypes.c_uint32),
        ("h2a", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("qx", ctypes.POINTER(ctypes.c_int32)),
        ("qy", ctypes.POINTER(ctypes.c_int32)),
        ("psx", ctypes.POINTER(ctypes.c_int32)),
        ("psy", ctypes.POINTER(ctypes.c_int32)),
    ]


class FastFilter:
    def __init__(self, models, bound, previous_bound=0, library=None):
        self.bound = bound
        self.previous_bound = previous_bound
        self.size = 2 * bound + 1
        count = len(models)
        self.model_data = (FilterModel * count)()
        self.arrays = []
        for index, (prime, k, a, ps, qs, h2, constant) in enumerate(models):
            qx = np.empty(self.size, dtype=np.int32)
            qy = np.empty(self.size, dtype=np.int32)
            psx = np.empty(self.size, dtype=np.int32)
            psy = np.empty(self.size, dtype=np.int32)
            for i, coefficient in enumerate(range(-bound, bound + 1)):
                q = qs[coefficient]
                qx[i] = 0 if q is None else q[0]
                qy[i] = 0 if q is None else q[1]
                p = ps[coefficient]
                psx[i] = -1 if p is None else p[0]
                psy[i] = -1 if p is None else p[1]
            self.arrays.append((qx, qy, psx, psy))
            e = (k * k - 1)**2 % prime
            ch = constant * h2 % prime
            self.model_data[index] = FilterModel(
                prime, a, h2, e, ch, e * h2 % prime,
                a * a % prime, ch * a % prime, h2 * a % prime, 0,
                qx.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                qy.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                psx.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                psy.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            )
        self.remaining = np.zeros((2, self.size), dtype=np.uint8)
        self.remaining_pointer = self.remaining.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
        self.lib = ctypes.CDLL(str(library or ROOT / "elliptic_filter.so"))
        self.lib.filter_pass.restype = ctypes.c_uint64
        self.lib.filter_pass.argtypes = [
            ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
            ctypes.c_int32, ctypes.POINTER(FilterModel), ctypes.POINTER(ctypes.c_uint8),
        ]
        self.last_count = 0

    def __len__(self):
        return len(self.model_data)

    def passes(self, n):
        if not -self.bound <= n <= self.bound:
            raise ValueError("coefficient outside filter bound")
        self.last_count = self.lib.filter_pass(
            self.size, self.bound, n + self.bound, self.previous_bound,
            len(self.model_data), self.model_data, self.remaining_pointer,
        )
        return self.remaining
