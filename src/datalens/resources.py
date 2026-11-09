"""Hardware detection and memory estimates (best effort, no extra dependencies).

RAM detection order: psutil (if installed) -> /proc/meminfo (Linux) -> Windows
GlobalMemoryStatusEx via ctypes. The Windows branch could NOT be exercised in the Linux
development sandbox; if it fails the functions return None rather than guessing.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any


def _memory_bytes() -> tuple[int | None, int | None]:
    """Return (total_bytes, available_bytes), either may be None."""
    try:
        import psutil  # optional

        vm = psutil.virtual_memory()
        return int(vm.total), int(vm.available)
    except Exception:
        pass
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                key, val = line.split(":", 1)
                info[key] = int(val.split()[0]) * 1024
        return info.get("MemTotal"), info.get("MemAvailable")
    except Exception:
        pass
    try:
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _Status()
        st.dwLength = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return int(st.ullTotalPhys), int(st.ullAvailPhys)
    except Exception:
        pass
    return None, None


def total_ram_gb() -> float | None:
    t, _ = _memory_bytes()
    return None if t is None else round(t / 1024**3, 2)


def available_ram_gb() -> float | None:
    _, a = _memory_bytes()
    return None if a is None else round(a / 1024**3, 2)


def estimate_matrix_gb(rows: int, columns: int, bytes_per_value: int = 8) -> float:
    """Size of a dense numeric matrix. This is ONE copy; pipelines hold several at once."""
    return round(rows * columns * bytes_per_value / 1024**3, 3)


def hardware_summary() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "total_ram_gb": total_ram_gb(),
        "available_ram_gb": available_ram_gb(),
    }
